"""tech_stack_extract Skill 实现与自注册。

触发条件：job_type 不在 ops/mgmt 中，且 JD 文本 ≥ 200 字
目标：从 JD 中提取完整技术栈，含类别、必需度、年限要求和原文依据
"""

from __future__ import annotations

from typing import ClassVar

from jobpilot_agent.integrations.llm_client import TokenUsage, get_llm_client
from jobpilot_agent.skills.base import SkillMetadata, SkillOutput
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.llm_skill_base import LLMSkillBase
from jobpilot_agent.skills.registry import registry
from jobpilot_agent.skills.tech_stack_extract.prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from jobpilot_agent.skills.tech_stack_extract.schemas import TechStackExtractData

_NON_TECH_JOB_TYPES = frozenset({"ops", "mgmt", "hr", "finance", "legal"})

_MIN_JD_LENGTH = 200


class TechStackExtractSkill(LLMSkillBase):
    """从 JD 文本中提取完整技术栈的 LLM Skill。

    should_invoke 策略：
    - 排除运营/管理类岗位（这些岗位没有实质技术栈要求）
    - JD 文本过短（< 200 字）时跳过，避免无效 LLM 调用
    """

    metadata: ClassVar[SkillMetadata] = SkillMetadata(
        name="tech_stack_extract",
        version="0.1.0",
        description="从职位描述中提取完整技术栈（编程语言、框架、数据库、DevOps 工具等）",
        when_to_use=(
            "当 JD 属于技术岗位（开发/算法/数据/测试/架构等）且文本长度 ≥ 200 字时调用。"
            "输出结果可直接用于技能匹配、差距分析和面试题生成。"
        ),
        when_not_to_use=(
            "运营、管理、HR、财务、法务等非技术岗位不应调用（job_type in ops/mgmt/hr/…）。"
            "JD 文本过短（< 200 字）或内容为空时跳过，避免无效调用。"
        ),
        tags=["llm", "tech_stack", "jd_analysis"],
    )

    def should_invoke(self, ctx: JDContext) -> bool:
        """当 job_type 非运营/管理类 且 JD 文本 ≥ 200 字时触发。"""
        if ctx.classification is None:
            return False
        if ctx.job_type in _NON_TECH_JOB_TYPES:
            return False
        return len(ctx.jd_text) >= _MIN_JD_LENGTH

    async def _run_llm(self, ctx: JDContext) -> tuple[TechStackExtractData, TokenUsage]:
        """调用 LLM 提取技术栈。

        Returns:
            Tuple of (TechStackExtractData, TokenUsage)。
        """
        client = get_llm_client()
        result, usage = await client.chat_json(
            system=SYSTEM_PROMPT,
            user=build_user_prompt(ctx.jd_text),
            schema=TechStackExtractData,
            model=ctx.llm_model,
            temperature=0.0,
            max_tokens=2000,
        )
        return result, usage  # type: ignore[return-value]


# ── 自注册 ──────────────────────────────────────────────────────────────────
registry.register(TechStackExtractSkill())
