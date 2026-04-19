"""Skill 模板实现。

复制整个 skill_template/ 目录到新目录后：
1. 修改目录名（如 tech_stack_extract/）
2. 修改 metadata.name
3. 实现 should_invoke 和 invoke
4. 更新 SKILL.md
5. 在 registry.py 的 register_all_skills() 中加 import
"""

from __future__ import annotations

import time
from typing import ClassVar, Type

from pydantic import BaseModel

from jobpilot_agent.skills.base import Skill, SkillExample, SkillMetadata, SkillOutput
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.registry import registry


# ── 输入/输出 Schema ─────────────────────────────────────────────────────────


class TemplateInput(BaseModel):
    """TemplateSkill 的 LangChain Tool 输入 Schema。"""

    jd_text: str
    request_id: str = "tool_call"
    user_id: str = "unknown"


class TemplateOutputData(BaseModel):
    """TemplateSkill 的业务输出 Schema（对应 SkillOutput.data 字段）。"""

    field_a: str = ""
    field_b: list[str] = []


# ── Skill 实现 ────────────────────────────────────────────────────────────────


class TemplateSkill(Skill):
    """模板 Skill，演示 Skill 开发规范。

    这是对业务无实际效果的示例实现，用于：
    - 验证 SkillRegistry / SkillDispatcher 功能
    - 作为新 Skill 的开发起点
    - 调试端点 GET /api/v1/skills 展示已注册 Skill
    """

    metadata: ClassVar[SkillMetadata] = SkillMetadata(
        name="template_skill",
        version="0.1.0",
        description="示例 Skill，演示 Skill 开发规范，不产生实际业务效果",
        when_to_use=(
            "当需要验证 Skill 基础设施是否正常工作时使用。"
            "实际场景：技术岗 JD 且需要功能演示。"
        ),
        when_not_to_use=(
            "生产环境中不应使用此 Skill。"
            "任何真实业务场景都应使用具体 Skill（如 tech_stack_extract）。"
        ),
        examples=[
            SkillExample(
                scenario="技术岗 JD，用于演示 Skill 调用流程",
                context_summary="job_type=tech, level=middle",
                expected_output="data.field_a='template output', data.field_b=['item1']",
                should_invoke=True,
            ),
            SkillExample(
                scenario="产品岗 JD，template_skill 不适用",
                context_summary="job_type=product",
                expected_output="should_invoke=False，跳过",
                should_invoke=False,
            ),
        ],
        tags=[],
        dependencies=[],
    )

    input_schema: ClassVar[Type[BaseModel]] = TemplateInput
    output_data_schema: ClassVar[Type[BaseModel]] = TemplateOutputData

    def should_invoke(self, ctx: JDContext) -> bool:
        """仅对技术岗启用（演示目的）。

        规则：classification.job_type == "tech"
        classification 为 None 时安全返回 False。
        """
        return ctx.job_type == "tech"

    async def invoke(self, ctx: JDContext) -> SkillOutput:
        """执行模板 Skill 逻辑（无实际业务效果）。

        演示正确的 invoke 实现模式：
        - 记录开始时间
        - 用 try/except 包裹所有逻辑
        - 填充 latency_ms
        - 返回 SkillOutput，不抛异常
        """
        start = time.monotonic()
        try:
            data = TemplateOutputData(
                field_a=f"template output for: {ctx.jd_text[:30]}...",
                field_b=["item1", "item2"],
            )
            return SkillOutput(
                skill_name=self.metadata.name,
                success=True,
                data=data.model_dump(),
                latency_ms=self._measure_ms(start),
            )
        except Exception as exc:  # noqa: BLE001
            return SkillOutput.make_error(
                skill_name=self.metadata.name,
                error_code="SKILL_ERROR",
                message=str(exc),
                latency_ms=self._measure_ms(start),
            )


# ── 自注册（module import 时执行）─────────────────────────────────────────────
registry.register(TemplateSkill())
