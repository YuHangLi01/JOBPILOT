"""gpa_check 正则快速抽取工具。

第一路（快速正则）：无 LLM 开销，< 1ms 命中显性信号。
第二路（LLM）：将正则结果拼入 user prompt，让 LLM 补全隐性要求。

正则覆盖：
- GPA / 绩点门槛（数字格式）
- 985 / 211 / 双一流 / C9 等院校层次
- 学历层次（本科 / 专科 / 硕士 / 博士 / 研究生）
- 排名要求（前 X%，top N%）
"""

from __future__ import annotations

import re
from typing import Any

# ── 正则模式 ─────────────────────────────────────────────────────────────────

_GPA_PATTERN = re.compile(
    r"(?:GPA|绩点|学业绩点|成绩绩点)"  # 关键词
    r"\s*[≥>=＞＝]?\s*"              # 可选比较符
    r"(\d+(?:[.,]\d+)?)"             # 数字门槛
    r"\s*(?:/\s*(\d+(?:[.,]\d+)?))?",  # 可选满分（/5.0）
    re.IGNORECASE,
)

_SCHOOL_TIER_PATTERN = re.compile(
    r"(985|211|双一流|C9联盟|C9|世界(?:一流|顶尖)|顶尖高校|重点院校)",
    re.IGNORECASE,
)

_DEGREE_PATTERN = re.compile(
    r"(博士|PhD|Doctor|硕士|研究生|Master|MBA|MPA|本科|学士|Bachelor|大专|专科|Associate)",
    re.IGNORECASE,
)

_RANK_PATTERN = re.compile(
    r"(?:成绩|排名|专业排名|班级排名)\s*(?:位于\s*)?(?:前|top)\s*(\d+)\s*[%％]",
    re.IGNORECASE,
)

_TRIGGER_KEYWORDS = re.compile(
    r"GPA|绩点|985|211|双一流|学历|成绩|专业排名|硕士|博士",
    re.IGNORECASE,
)

# ── 公共 API ─────────────────────────────────────────────────────────────────


def has_education_signals(text: str) -> bool:
    """快速判断 JD 是否含学历/绩点相关信号词（用于 should_invoke）。

    Args:
        text: JD 原始文本。

    Returns:
        True 表示发现至少一个学历/绩点信号词。
    """
    return bool(_TRIGGER_KEYWORDS.search(text))


def extract_gpa_signals(text: str) -> dict[str, Any]:
    """从 JD 文本中快速提取显性学历/绩点信号。

    返回结构供 LLM prompt 拼接使用，让 LLM 聚焦在"隐性"部分。

    Args:
        text: JD 原始文本。

    Returns:
        包含以下字段的字典：
        - gpa_mentions: list[dict]，每条含 threshold/full_score/quote
        - school_tiers: list[str]，如 ["985", "211"]
        - degree_mentions: list[str]，如 ["硕士", "本科"]
        - rank_mentions: list[dict]，每条含 percentage/quote
    """
    signals: dict[str, Any] = {
        "gpa_mentions": [],
        "school_tiers": [],
        "degree_mentions": [],
        "rank_mentions": [],
    }

    # GPA / 绩点
    for m in _GPA_PATTERN.finditer(text):
        threshold = m.group(1).replace(",", ".")
        full_score = m.group(2)
        if full_score:
            full_score = full_score.replace(",", ".")
            value_str = f"{threshold}/{full_score}"
        else:
            value_str = threshold
        signals["gpa_mentions"].append(
            {
                "threshold": threshold,
                "full_score": full_score,
                "value": value_str,
                "quote": m.group(0),
            }
        )

    # 院校层次
    for m in _SCHOOL_TIER_PATTERN.finditer(text):
        tier = m.group(1)
        if tier not in signals["school_tiers"]:
            signals["school_tiers"].append(tier)

    # 学历
    seen_degrees: set[str] = set()
    for m in _DEGREE_PATTERN.finditer(text):
        degree = m.group(1)
        if degree not in seen_degrees:
            signals["degree_mentions"].append(degree)
            seen_degrees.add(degree)

    # 排名
    for m in _RANK_PATTERN.finditer(text):
        signals["rank_mentions"].append(
            {
                "percentage": int(m.group(1)),
                "quote": m.group(0),
            }
        )

    return signals
