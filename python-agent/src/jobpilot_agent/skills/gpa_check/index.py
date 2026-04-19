"""gpa_check Skill 实现与自注册。

触发条件：channel == "campus" 且 JD 含学历/绩点信号关键词
策略：正则快速提取显性信号 → 拼入 LLM prompt → LLM 补全隐性要求
"""

from __future__ import annotations

from typing import ClassVar

from jobpilot_agent.integrations.llm_client import TokenUsage, get_llm_client
from jobpilot_agent.skills.base import SkillMetadata, SkillOutput
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.gpa_check.prompts import SYSTEM_PROMPT, build_user_prompt
from jobpilot_agent.skills.gpa_check.regex_rules import (
    extract_gpa_signals,
    has_education_signals,
)
from jobpilot_agent.skills.gpa_check.schemas import GPACheckData
from jobpilot_agent.skills.llm_skill_base import LLMSkillBase
from jobpilot_agent.skills.registry import registry


class GPACheckSkill(LLMSkillBase):
    """校招 JD GPA / 学历要求检测 Skill。

    双路策略：
    1. 正则（regex_rules.py）快速提取显性 GPA/院校层次/学历信号
    2. 将正则结果拼入 LLM prompt，LLM 负责识别隐性要求并输出结构化数据

    should_invoke 条件：
    - channel == "campus"（校招渠道）
    - JD 文本包含学历/绩点相关信号词
    """

    metadata: ClassVar[SkillMetadata] = SkillMetadata(
        name="gpa_check",
        version="0.1.0",
        description=(
            "检测校招 JD 中的 GPA / 绩点 / 学历门槛要求，"
            "识别显性要求（正则）和隐性要求（LLM 推断）"
        ),
        when_to_use=(
            "当 JD 渠道为校园招聘（channel=campus）且文本中包含 GPA、绩点、"
            "985/211、学历等信号词时调用。"
            "结果用于告知应聘者是否满足学历门槛，提前过滤不符合岗位。"
        ),
        when_not_to_use=(
            "社会招聘（channel=social）无需 GPA 分析。"
            "JD 中完全没有任何学历相关词汇时跳过，避免无效 LLM 调用。"
        ),
        tags=["llm", "campus", "gpa", "education"],
    )

    def should_invoke(self, ctx: JDContext) -> bool:
        """当 channel=campus 且 JD 含学历信号时触发。"""
        if ctx.channel != "campus":
            return False
        return has_education_signals(ctx.jd_text)

    async def _run_llm(self, ctx: JDContext) -> tuple[GPACheckData, TokenUsage]:
        """双路策略：正则提取信号 → LLM 结构化 + 补全隐性要求。"""
        signals = extract_gpa_signals(ctx.jd_text)

        client = get_llm_client()
        result, usage = await client.chat_json(
            system=SYSTEM_PROMPT,
            user=build_user_prompt(ctx.jd_text, signals),
            schema=GPACheckData,
            model=ctx.llm_model,
            temperature=0.0,
            max_tokens=1500,
        )
        return result, usage  # type: ignore[return-value]


# ── 自注册 ──────────────────────────────────────────────────────────────────
registry.register(GPACheckSkill())
