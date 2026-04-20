"""en_translate Skill 输出 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EnTranslateData(BaseModel):
    """en_translate Skill 完整输出。

    Attributes:
        jd_summary_en: JD 英文摘要（150–300 词），面向英语母语阅读者。
        jd_summary_zh: JD 中文摘要（150–300 字），与 jd_summary_en 内容对应。
        resume_bullets_en: 针对该岗位的英文简历要点（STAR 格式），3–5 条。
        key_terms_en: 岗位高频关键词英文列表（5–10 个），用于简历 ATS 优化。
        tone: JD 语气风格评估，如 "formal"、"casual"、"technical"。
    """

    jd_summary_en: str = Field(
        description=(
            "JD 英文摘要，150–300 词，面向英语母语读者，"
            "涵盖岗位职责、核心技能要求和公司背景"
        )
    )
    jd_summary_zh: str = Field(
        description=(
            "JD 中文摘要，150–300 字，"
            "内容与 jd_summary_en 对应，供中文用户快速理解岗位"
        )
    )
    resume_bullets_en: list[str] = Field(
        description=(
            "针对该岗位的英文简历要点，3–5 条，每条采用 STAR 格式，"
            "以行动动词开头（如 Designed, Implemented, Led）"
        )
    )
    key_terms_en: list[str] = Field(
        description=(
            "岗位高频英文关键词 5–10 个，"
            "用于简历 ATS 关键词优化，如 ['Python', 'distributed systems', 'CI/CD']"
        )
    )
    tone: str = Field(
        default="formal",
        description="JD 语气风格：formal | casual | technical | startup | enterprise",
    )
