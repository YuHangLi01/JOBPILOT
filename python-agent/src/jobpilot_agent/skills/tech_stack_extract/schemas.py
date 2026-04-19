"""tech_stack_extract Skill 输出 Schema。

所有字段均有 description，供 LLM JSON mode 参考约束。
evidence_quote 强制来自原始 JD 文本，避免 LLM 幻觉。
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TechSkillItem(BaseModel):
    """单个技术技能条目。

    Attributes:
        name: 技术名称，如 "Python"、"React"、"Kubernetes"。
        category: 技术分类，如 "language"、"framework"、"database"、"devops"、"other"。
        required: 是否为必要技能（True=必须，False=加分项）。
        experience_years: 明确要求的年限；无明确要求时为 None。
        evidence_quote: 来自原始 JD 的原文片段（≤ 60 字），作为提取依据。
    """

    name: str = Field(description="技术名称，如 Python、React、PostgreSQL")
    category: str = Field(
        description="技术分类：language | framework | database | devops | cloud | tool | other"
    )
    required: bool = Field(description="是否为硬性要求（True=必须，False=加分项）")
    experience_years: Optional[int] = Field(
        default=None,
        description="明确要求的年限，如 '熟练掌握 Python 3 年以上' 则为 3；无明确要求时为 null",
    )
    evidence_quote: str = Field(
        description="来自原始 JD 文本的直接引用（≤ 60 字），不得自行生成"
    )


class TechStackExtractData(BaseModel):
    """tech_stack_extract Skill 完整输出。

    Attributes:
        tech_stack: 提取到的技术技能列表，按 required 降序（必要项在前）。
        primary_language: 岗位主编程语言；无法判断时为 None。
        tech_complexity: 技术栈复杂度主观评分 (1–5)，5 分最复杂。
        summary: 对技术栈的一句话总结（≤ 50 字）。
    """

    tech_stack: list[TechSkillItem] = Field(
        default_factory=list,
        description="提取到的技术技能列表，required=True 的项目排在前面",
    )
    primary_language: Optional[str] = Field(
        default=None,
        description="主要编程语言（如 Python、Java、TypeScript），无法确定时为 null",
    )
    tech_complexity: int = Field(
        default=3,
        ge=1,
        le=5,
        description="技术栈复杂度评分：1=极简单，3=中等，5=非常复杂",
    )
    summary: str = Field(
        default="",
        description="对该岗位技术栈的一句话中文总结（≤ 50 字）",
    )
