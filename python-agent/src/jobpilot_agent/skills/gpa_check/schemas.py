"""gpa_check Skill 输出 Schema。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EducationRequirement(BaseModel):
    """单条学历/绩点要求。

    Attributes:
        req_type: 要求类型。
        value: 具体门槛值（字符串，如 "3.5/5.0", "985", "硕士"）。
        required: 是否为硬性要求。
        implicit: 是否为隐性要求（正则未直接命中，由 LLM 推断）。
        evidence_quote: 来自 JD 原文的依据（显性要求必填；隐性要求可为 None）。
    """

    req_type: str = Field(
        description="要求类型：gpa | school_tier | degree | major | other"
    )
    value: str = Field(description="具体门槛，如 '3.5/5.0'、'985/211'、'本科及以上'")
    required: bool = Field(description="是否硬性要求")
    implicit: bool = Field(
        default=False,
        description="是否为隐性要求（正则未直接命中，LLM 从上下文推断）",
    )
    evidence_quote: Optional[str] = Field(
        default=None,
        description="来自 JD 原文的直接引用（显性要求必填；隐性可为 null）",
    )


class GPACheckData(BaseModel):
    """gpa_check Skill 完整输出。

    Attributes:
        requirements: 所有学历/绩点要求列表。
        has_gpa_requirement: 是否含明确 GPA 要求。
        has_school_tier_requirement: 是否含985/211/双一流等层次要求。
        min_degree: 最低学历要求（如 "本科", "硕士", "博士"）；无时为 None。
        overall_strictness: 整体学历门槛严格程度 (1–5)，5 最严格。
        notes: 补充说明（≤ 100 字）。
    """

    requirements: list[EducationRequirement] = Field(
        default_factory=list,
        description="所有学历/绩点要求条目，显性在前，隐性在后",
    )
    has_gpa_requirement: bool = Field(
        default=False,
        description="是否含明确 GPA / 绩点要求",
    )
    has_school_tier_requirement: bool = Field(
        default=False,
        description="是否含 985 / 211 / 双一流等院校层次要求",
    )
    min_degree: Optional[str] = Field(
        default=None,
        description="最低学历要求：本科 | 硕士 | 博士 | null（无明确要求）",
    )
    overall_strictness: int = Field(
        default=2,
        ge=1,
        le=5,
        description="学历门槛整体严格程度：1=无要求，3=一般，5=极严格",
    )
    notes: str = Field(
        default="",
        description="补充说明，如隐性要求的推断依据（≤ 100 字）",
    )
