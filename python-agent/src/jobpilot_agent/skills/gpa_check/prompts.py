"""gpa_check Skill 提示词模板。

双路策略：
1. 正则先跑，提取显性信号（GPA 数字、985/211、学历）
2. 正则结果拼入 user prompt，LLM 负责补全"隐性要求"并结构化输出
"""

from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = """\
你是招聘分析专家，专门识别校招 JD 中的学历和 GPA 要求。

## 任务
基于正则预提取的显性信号和完整 JD 文本，输出结构化的学历/绩点要求分析。

## 重点关注
1. **显性要求**：JD 明文写出（正则已预提取，你需要结构化）
2. **隐性要求**：未直接写明但可从上下文推断，如：
   - "优秀应届生" 可能隐含绩点前 30%
   - "顶尖高校" 可能隐含 985/211
   - 竞赛/奖学金经历隐含高 GPA 期望

## 输出格式（严格 JSON）
{
  "requirements": [
    {
      "req_type": "gpa|school_tier|degree|major|other",
      "value": "门槛值字符串",
      "required": true|false,
      "implicit": false（显性）或 true（隐性）,
      "evidence_quote": "原文引用或null"
    }
  ],
  "has_gpa_requirement": true|false,
  "has_school_tier_requirement": true|false,
  "min_degree": "本科|硕士|博士|null",
  "overall_strictness": 1到5的整数,
  "notes": "补充说明（≤100字）"
}

规则：
- 若正则已提取到显性信号，直接结构化，不得改变事实
- 隐性要求需在 notes 中说明推断依据
- 若 JD 无任何学历要求，返回 requirements=[] 和低 overall_strictness
"""


def build_user_prompt(jd_text: str, signals: dict[str, Any]) -> str:
    """将正则结果和 JD 原文组合成 user prompt。

    Args:
        jd_text: 原始 JD 文本。
        signals: extract_gpa_signals() 返回的正则信号字典。

    Returns:
        完整 user prompt 字符串。
    """
    signals_json = json.dumps(signals, ensure_ascii=False, indent=2)

    return f"""## 正则预提取的显性信号
```json
{signals_json}
```

## 完整 JD 文本
---
{jd_text}
---

请基于以上信息，输出符合 JSON 格式要求的学历/绩点分析结果。"""
