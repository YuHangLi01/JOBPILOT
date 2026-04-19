"""tech_stack_extract Skill 的提示词模板。

设计原则：
- System prompt 明确输出格式约束（JSON schema 内嵌）
- User prompt 包含 2 个 few-shot 示例，覆盖"前端岗" + "算法岗"
- evidence_quote 严格要求引用原文，减少 LLM 幻觉
- 使用 f-string 模板，占位符用 {jd_text}
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
你是一位经验丰富的技术招聘分析师，专门从职位描述（JD）中提取技术栈信息。

## 任务
从用户提供的 JD 文本中，提取所有明确或隐含的技术技能要求，输出严格合法的 JSON。

## 输出格式
必须输出以下 JSON 结构，不得添加额外字段：
{
  "tech_stack": [
    {
      "name": "技术名称（string）",
      "category": "language|framework|database|devops|cloud|tool|other",
      "required": true|false,
      "experience_years": null或整数,
      "evidence_quote": "来自JD的直接引用（≤60字）"
    }
  ],
  "primary_language": "主编程语言或null",
  "tech_complexity": 1到5的整数,
  "summary": "一句话总结（≤50字）"
}

## 关键规则
1. evidence_quote 必须是 JD 原文的直接片段，不得改写或虚构
2. required=true：JD 写明"必须"/"熟悉"/"掌握"等强要求
3. required=false：JD 写"了解"/"加分"/"优先"等软要求
4. 若无法提取任何技术技能，返回 tech_stack=[]
5. 不相关内容（薪资/地点/福利）一律忽略
"""

FEW_SHOT_EXAMPLES = """\
## 示例 1：前端工程师 JD

JD 文本：
---
职位：前端工程师（React 方向）
技术要求：
- 精通 JavaScript / TypeScript，3 年以上前端开发经验
- 熟悉 React 18 及 Hooks，了解 Next.js 优先
- 熟悉 CSS3 / Sass，有 TailwindCSS 使用经验者优先
- 了解 Node.js 后端基础，会写简单接口
- 使用过 Git 进行团队协作
---

期望输出：
{
  "tech_stack": [
    {"name": "TypeScript", "category": "language", "required": true, "experience_years": 3, "evidence_quote": "精通 JavaScript / TypeScript，3 年以上前端开发经验"},
    {"name": "JavaScript", "category": "language", "required": true, "experience_years": 3, "evidence_quote": "精通 JavaScript / TypeScript，3 年以上前端开发经验"},
    {"name": "React", "category": "framework", "required": true, "experience_years": null, "evidence_quote": "熟悉 React 18 及 Hooks"},
    {"name": "Next.js", "category": "framework", "required": false, "experience_years": null, "evidence_quote": "了解 Next.js 优先"},
    {"name": "CSS3", "category": "tool", "required": true, "experience_years": null, "evidence_quote": "熟悉 CSS3 / Sass"},
    {"name": "Sass", "category": "tool", "required": true, "experience_years": null, "evidence_quote": "熟悉 CSS3 / Sass"},
    {"name": "TailwindCSS", "category": "framework", "required": false, "experience_years": null, "evidence_quote": "有 TailwindCSS 使用经验者优先"},
    {"name": "Node.js", "category": "language", "required": false, "experience_years": null, "evidence_quote": "了解 Node.js 后端基础"},
    {"name": "Git", "category": "tool", "required": true, "experience_years": null, "evidence_quote": "使用过 Git 进行团队协作"}
  ],
  "primary_language": "TypeScript",
  "tech_complexity": 3,
  "summary": "React 全栈前端岗，以 TypeScript + React 18 为核心，兼顾 Node.js 与 CSS 工具链"
}

## 示例 2：算法工程师 JD

JD 文本：
---
职位：推荐算法工程师
要求：
- 硕士及以上学历，计算机/统计/数学相关专业
- 熟练使用 Python，掌握 pandas、numpy、scikit-learn
- 了解深度学习框架 PyTorch 或 TensorFlow
- 熟悉推荐系统算法（协同过滤、矩阵分解、双塔模型）
- 有 Spark/Flink 大数据处理经验者优先
- 熟悉 Linux 环境，会使用 Docker
---

期望输出：
{
  "tech_stack": [
    {"name": "Python", "category": "language", "required": true, "experience_years": null, "evidence_quote": "熟练使用 Python"},
    {"name": "pandas", "category": "tool", "required": true, "experience_years": null, "evidence_quote": "掌握 pandas、numpy、scikit-learn"},
    {"name": "numpy", "category": "tool", "required": true, "experience_years": null, "evidence_quote": "掌握 pandas、numpy、scikit-learn"},
    {"name": "scikit-learn", "category": "framework", "required": true, "experience_years": null, "evidence_quote": "掌握 pandas、numpy、scikit-learn"},
    {"name": "PyTorch", "category": "framework", "required": false, "experience_years": null, "evidence_quote": "了解深度学习框架 PyTorch 或 TensorFlow"},
    {"name": "TensorFlow", "category": "framework", "required": false, "experience_years": null, "evidence_quote": "了解深度学习框架 PyTorch 或 TensorFlow"},
    {"name": "Spark", "category": "devops", "required": false, "experience_years": null, "evidence_quote": "有 Spark/Flink 大数据处理经验者优先"},
    {"name": "Flink", "category": "devops", "required": false, "experience_years": null, "evidence_quote": "有 Spark/Flink 大数据处理经验者优先"},
    {"name": "Docker", "category": "devops", "required": true, "experience_years": null, "evidence_quote": "熟悉 Linux 环境，会使用 Docker"}
  ],
  "primary_language": "Python",
  "tech_complexity": 4,
  "summary": "推荐算法岗，以 Python 数据科学栈为核心，兼顾深度学习框架与大数据处理工具"
}
"""


def build_user_prompt(jd_text: str) -> str:
    """构建实际的 user prompt，拼入 few-shot 示例和待分析 JD。

    Args:
        jd_text: 原始 JD 文本。

    Returns:
        完整的 user prompt 字符串。
    """
    return f"""{FEW_SHOT_EXAMPLES}

## 现在请分析以下 JD

JD 文本：
---
{jd_text}
---

请输出符合要求的 JSON，不要有任何额外解释文字。"""
