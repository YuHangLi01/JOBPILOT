"""interview_rag Skill 提示词模板。

设计原则：
- 输入：真实面经 turn 列表（来自 RAG 检索）
- 输出：结构化面试题（question + intent + answer_points）
- 每道题必须绑定 rag_source_doc_ids，防止 LLM 幻觉
- 出题意图要具体到「考察什么能力」
- 回答要点要可直接练习（3-5 条）
"""

from __future__ import annotations

from jobpilot_agent.retrieval.types import RetrievalResult

SYSTEM_PROMPT = """\
你是一位专业的面试教练，擅长从真实面经中提炼高价值面试题，帮助候选人系统准备。

## 任务
基于候选人提供的真实面经片段，为特定岗位生成结构化面试准备清单。

## 输出格式（严格 JSON）
{
  "retrieved_count": 已检索到的面经数量（整数，来自输入），
  "questions": [
    {
      "question": "完整面试题文本",
      "source_company": "来源公司名",
      "source_stage": "tech_qa|project_deep_dive|scenario|hr|unknown",
      "intent": "具体出题意图，说明考察什么能力或知识点（≤ 50 字）",
      "answer_points": ["要点1（可直接练习）", "要点2", "要点3"],
      "rag_source_doc_ids": ["doc_id_1", "doc_id_2"],
      "rag_score": 0.85
    }
  ],
  "coverage_note": "检索说明（可为 null）",
  "retrieval_metadata": {}
}

## 关键规则
1. rag_source_doc_ids 必须填写，只能使用输入面经片段中的 doc_id，**绝不能虚构**
2. 每道题的 answer_points 要具体可操作，不要泛泛而谈（如"深入理解"等）
3. 出题 intent 要具体，如"考察候选人对 Redis 主从复制机制的理解"而非"考察 Redis"
4. 优先提取 tech_qa 和 project_deep_dive 阶段的高价值题目
5. 生成 5–8 道题，覆盖不同技术深度（基础 + 进阶 + 项目实战）
6. 去重：多个面经来源指向同一知识点时，合并为一道题，doc_ids 全部列出
"""


def build_user_prompt(
    company: str,
    position: str,
    results: list[RetrievalResult],
) -> str:
    """将 RAG 检索结果格式化为 LLM user prompt。

    Args:
        company: 岗位公司名。
        position: 岗位名称。
        results: 检索到的面经 turn 列表（已去重）。

    Returns:
        完整 user prompt 字符串。
    """
    context_items = []
    for r in results:
        meta = r.metadata
        doc_company = meta.get("company", company or "未知")
        stage = meta.get("stage", "unknown")
        context_items.append(
            f"[doc_id={r.doc_id}] [company={doc_company}] [stage={stage}] [score={r.score:.3f}]\n{r.text}"
        )

    context_block = "\n\n---\n\n".join(context_items)

    return f"""## 目标岗位
- 公司：{company or "（未知）"}
- 岗位：{position or "（未知）"}

## 检索到的真实面经片段（共 {len(results)} 条）

{context_block}

---

请基于以上真实面经，为该岗位生成 5–8 道高价值面试题。
记住：rag_source_doc_ids 只能引用上面列出的 doc_id，不得虚构。
输出符合要求的 JSON，不要有任何额外说明文字。"""
