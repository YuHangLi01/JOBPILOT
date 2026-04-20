"""final_synthesis 节点使用的提示词。

职责：基于所有 Skill 的输出数据，生成最终的结构化分析报告。
输出：JSON，对应 JDRoutingResults 的字段结构。

设计约束：
- LLM 只能使用 skill_data 中已有的信息，不得凭空捏造。
- 若某项 Skill 数据不存在，对应字段使用空列表或空字符串，不要编造。
"""

import json

SYSTEM_PROMPT = """\
你是一个求职辅导专家，擅长分析 JD 和生成求职建议。

## 任务

根据已完成的 JD 分析数据，生成最终的结构化求职建议报告。

## 输出格式

返回合法 JSON，结构如下：

{
  "jd_summary": "对本职位的 2-4 句话综合概述，覆盖：职位核心职责、关键技能要求、公司亮点、适合人群",
  "resume_advice": [
    {
      "priority": "high | medium | low",
      "advice": "简历优化建议（1-2句，具体可操作）",
      "related_jd_requirement": "对应的 JD 要求原文（选填）"
    }
  ],
  "interview_questions": [
    {
      "question": "面试题（完整句子）",
      "intent": "考察意图（1句话）",
      "answer_points": ["答题要点1", "答题要点2", "答题要点3"]
    }
  ]
}

## 规则

1. **只使用 skill_data 中提供的信息**。若 skill_data 为空或某字段缺失，对应字段返回空列表或 ""，绝不捏造数据。
2. resume_advice 按 priority 排列（high 优先），最多 5 条。
3. interview_questions 最多 5 条，每条 answer_points 2-4 个要点。
4. jd_summary 必须基于 parsed_jd 和 classification 数据生成，不得超过 200 字。
5. 只返回 JSON，不加解释说明。
"""


def _compact_skill_data(merged_skill_data: dict) -> dict:
    """对每个 Skill 的原始 data 做结构化压缩，仅保留 LLM 合成所需关键字段。

    设计目标：把 user prompt 从 ~3000 tokens 降到 ~1200 tokens（-60%），
    直接减少 final_synthesis 的延迟和单次调用成本。

    未识别的 skill 名原样透传（防止新增 skill 时静默丢数据）。

    Args:
        merged_skill_data: {skill_name: skill_data_dict}

    Returns:
        裁剪后的 {skill_name: compact_dict}
    """
    if not isinstance(merged_skill_data, dict):
        return {}

    compact: dict = {}
    for name, data in merged_skill_data.items():
        if not isinstance(data, dict):
            compact[name] = data
            continue

        if name == "tech_stack_extract":
            compact[name] = {
                "primary": [
                    s.get("name") if isinstance(s, dict) else s
                    for s in (data.get("primary_stack") or [])
                ][:8],
                "preferred": [
                    s.get("name") if isinstance(s, dict) else s
                    for s in (data.get("preferred_stack") or [])
                ][:5],
            }
        elif name == "interview_rag":
            questions = data.get("questions") or data.get("interview_questions") or []
            compact[name] = {
                "top_questions": [
                    {
                        "question": q.get("question", ""),
                        "intent": q.get("intent", ""),
                    }
                    if isinstance(q, dict)
                    else {"question": str(q)}
                    for q in questions[:5]
                ],
                "retrieved_count": data.get("retrieved_count", 0),
            }
        elif name == "github_scan":
            compact[name] = {
                "username": data.get("username"),
                "signals": data.get("signals") or data.get("highlights") or [],
                "score": data.get("score"),
            }
        elif name == "portfolio_check":
            compact[name] = {
                "has_portfolio": data.get("has_portfolio", False),
                "summary": data.get("summary") or data.get("note") or "",
            }
        elif name == "gpa_check":
            compact[name] = {
                "required_gpa": data.get("required_gpa"),
                "threshold_note": data.get("threshold_note") or data.get("note") or "",
            }
        elif name == "en_translate":
            translated = data.get("translated_jd") or data.get("translation") or ""
            # 翻译结果本身可能很长，仅保留前 600 字；LLM 主要靠 parsed_jd 已结构化信息
            compact[name] = {
                "translation_excerpt": translated[:600] if isinstance(translated, str) else "",
                "source_lang": data.get("source_lang"),
            }
        else:
            compact[name] = data

    return compact


def build_user_prompt(
    parsed_jd: dict,
    classification: dict,
    merged_skill_data: dict,
) -> str:
    """构造 final_synthesis 的 user 提示词。

    对 merged_skill_data 做压缩，避免原始 evidence 塞爆 prompt。

    Args:
        parsed_jd: parse_jd 节点输出。
        classification: classify_jd 节点输出。
        merged_skill_data: merge_outputs 节点聚合的 {skill_name: data} 字典。

    Returns:
        格式化后的 user prompt 字符串。
    """
    compact_skill_data = _compact_skill_data(merged_skill_data)
    sections = [
        "## JD 解析结果",
        json.dumps(parsed_jd, ensure_ascii=False, indent=2),
        "",
        "## JD 分类结果",
        json.dumps(classification, ensure_ascii=False, indent=2),
        "",
        "## Skill 分析数据（精简版）",
        json.dumps(compact_skill_data, ensure_ascii=False, indent=2),
        "",
        "请基于以上数据生成最终求职建议报告（JSON 格式）：",
    ]
    return "\n".join(sections)
