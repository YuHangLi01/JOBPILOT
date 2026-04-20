"""portfolio_check Skill 输出 Schema。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PortfolioGap(BaseModel):
    """单条 JD 要求与作品集的覆盖分析。

    Attributes:
        jd_requirement: JD 的某项具体要求（从 JD 文本提取）。
        covered: 作品集是否覆盖该要求。
        coverage_evidence: 如覆盖，来自作品集的支撑内容（原文引用，≤ 100 字）。
        gap_suggestion: 如未覆盖，建议补充的具体内容。
    """

    jd_requirement: str = Field(description="JD 中的具体要求，如 '有 B 端产品设计经验'")
    covered: bool = Field(description="作品集是否覆盖该要求")
    coverage_evidence: Optional[str] = Field(
        default=None,
        description="如覆盖，作品集中支撑该要求的原文引用（≤ 100 字）",
    )
    gap_suggestion: Optional[str] = Field(
        default=None,
        description="如未覆盖，建议在作品集中补充的具体内容（≤ 80 字）",
    )


class PortfolioCheckData(BaseModel):
    """portfolio_check Skill 完整输出。

    Attributes:
        portfolio_summary: 作品集总体描述（200 字以内）。
        case_count: 作品集包含的项目案例数量。
        coverage_gaps: 逐条 JD 要求与作品集的覆盖分析。
        coverage_score: 整体覆盖度评分 [0.0, 1.0]。
        presentation_tips: 作品集呈现优化建议（3–5 条，具体可操作）。
    """

    portfolio_summary: str = Field(
        description="对作品集的一句话总结（≤ 200 字），涵盖主要案例类型和亮点"
    )
    case_count: int = Field(
        default=0,
        description="作品集中包含的独立项目案例数量",
    )
    coverage_gaps: list[PortfolioGap] = Field(
        default_factory=list,
        description="JD 各项要求的覆盖分析，covered=True 排在前面",
    )
    coverage_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="整体覆盖度：0.0=完全不覆盖，1.0=完全覆盖 JD 所有要求",
    )
    presentation_tips: list[str] = Field(
        default_factory=list,
        description="作品集呈现优化建议，如 '添加用户反馈数据'、'补充项目背景说明'（3–5 条）",
    )
