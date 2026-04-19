"""Skill 抽象基类及配套数据模型。

核心设计：
- Skill 对外暴露两套接口：
  1. 业务层接口（should_invoke / invoke）：供 LangGraph 条件边和 SkillDispatcher 调用
  2. LangChain Tool 接口（to_langchain_tool）：供 LLM tool-calling 动态决策

反模式约束（硬性要求，测试会检验）：
- should_invoke 必须是纯函数，不得调用 LLM 或异步 I/O
- invoke 不得抛原生异常，必须返回 SkillOutput(success=False, error=...)
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Optional, Type

from pydantic import BaseModel, Field

from jobpilot_agent.skills.context import JDContext


class SkillExample(BaseModel):
    """给人类与 LLM 都能看懂的正反例，用于 SKILL.md 和 LangChain Tool 描述。

    Attributes:
        scenario: 简述触发场景（一句话）。
        context_summary: 简述此时 JDContext 的关键字段值。
        expected_output: 期望 Skill 输出的简述。
        should_invoke: 该场景下 should_invoke 应返回的结果。
    """

    scenario: str
    context_summary: str
    expected_output: str
    should_invoke: bool


class SkillMetadata(BaseModel):
    """Skill 元信息——对应 SKILL.md 里的结构化字段。

    Attributes:
        name: Skill 唯一标识符（小写下划线，如 tech_stack_extract）。
        version: 语义化版本号。
        description: 一句话功能描述，LLM tool-calling 的核心依据。
        when_to_use: 触发条件描述，给 LLM 看的正例说明。
        when_not_to_use: 反例条件，帮 LLM 避免误调用。
        examples: 正反例列表。
        dependencies: 依赖其他 Skill 的名字（用于拓扑排序）。
        tags: 实现标签，如 ["llm", "rag", "external_api"]。
    """

    name: str
    version: str = "0.1.0"
    description: str
    when_to_use: str
    when_not_to_use: str
    examples: list[SkillExample] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class SkillOutput(BaseModel):
    """所有 Skill 输出的统一外壳。

    无论成功失败，invoke 都必须返回此对象（不抛异常）。

    Attributes:
        skill_name: 生成此输出的 Skill 名称。
        success: 执行是否成功。
        data: 业务数据，各 Skill 自定义 schema，通过 output_data_schema 声明。
        error: 失败时的错误信息（error_code: message 格式）。
        latency_ms: Skill 执行耗时（毫秒）。
        tokens_used: LLM token 消耗量（调用 LLM 时填充）。
        llm_calls: LLM API 调用次数。
        external_calls: 外部 API 调用次数（不含 LLM）。
    """

    skill_name: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

    latency_ms: int = 0
    tokens_used: int = 0
    llm_calls: int = 0
    external_calls: int = 0

    @classmethod
    def make_error(
        cls,
        skill_name: str,
        error_code: str,
        message: str,
        latency_ms: int = 0,
    ) -> "SkillOutput":
        """构造失败输出的便捷工厂方法。

        Args:
            skill_name: 失败的 Skill 名称。
            error_code: 结构化错误码（来自 errors.py）。
            message: 人类可读描述。
            latency_ms: 失败前已耗时。

        Returns:
            success=False 的 SkillOutput。
        """
        return cls(
            skill_name=skill_name,
            success=False,
            error=f"{error_code}: {message}",
            latency_ms=latency_ms,
        )


class Skill(ABC):
    """Skill 抽象基类。

    子类必须：
    1. 声明 `metadata: ClassVar[SkillMetadata]`
    2. 实现 `should_invoke(ctx) -> bool`（纯函数，不得调 LLM）
    3. 实现 `async invoke(ctx) -> SkillOutput`（捕获所有异常，不抛原生异常）

    子类可选：
    - 声明 `input_schema` / `output_data_schema` 用于 LangChain Tool 参数校验与文档

    Example:
        >>> class MySkill(Skill):
        ...     metadata = SkillMetadata(
        ...         name="my_skill",
        ...         description="做某事",
        ...         when_to_use="...",
        ...         when_not_to_use="...",
        ...     )
        ...     def should_invoke(self, ctx):
        ...         return ctx.job_type == "tech"
        ...     async def invoke(self, ctx):
        ...         return SkillOutput(skill_name="my_skill", success=True)
    """

    metadata: ClassVar[SkillMetadata]

    input_schema: ClassVar[Optional[Type[BaseModel]]] = None
    output_data_schema: ClassVar[Optional[Type[BaseModel]]] = None

    # ===== 业务层接口（LangGraph / SkillDispatcher 调用）=====

    @abstractmethod
    def should_invoke(self, ctx: JDContext) -> bool:
        """基于规则判断是否应调用该 Skill。

        严格约束：
        - 不得调用 LLM（保持 < 1ms 轻量）
        - 必须是纯函数（无副作用，无 I/O）
        - classification 为 None 时应安全返回 False

        Args:
            ctx: 当前请求的 JD 上下文。

        Returns:
            True 表示应调用，False 表示跳过。
        """
        ...

    @abstractmethod
    async def invoke(self, ctx: JDContext) -> SkillOutput:
        """执行 Skill 主逻辑。

        责任：
        - 自行处理超时（asyncio.wait_for，超时阈值参考 ctx.timeout_seconds）
        - 捕获所有 Exception，包装为 SkillOutput(success=False, error=...)
        - 绝不抛原生异常到调用方
        - 填充 latency_ms / tokens_used / llm_calls / external_calls

        Args:
            ctx: 当前请求的 JD 上下文。

        Returns:
            SkillOutput，无论成败均有效（success=False 时 error 字段有值）。
        """
        ...

    # ===== LangChain Tool 适配 =====

    def to_langchain_tool(self):  # type: ignore[return]
        """把 Skill 暴露成 LangChain StructuredTool，供 LLM tool-calling 动态决策。

        Tool 描述由 description + when_to_use + when_not_to_use 组合，
        帮助 LLM 更准确地决定是否调用该 Tool。

        Returns:
            langchain_core.tools.StructuredTool 实例。
        """
        from langchain_core.tools import StructuredTool  # type: ignore[import]

        full_description = (
            f"{self.metadata.description}\n\n"
            f"【何时使用】\n{self.metadata.when_to_use}\n\n"
            f"【何时不用】\n{self.metadata.when_not_to_use}"
        )

        skill_ref = self  # 闭包捕获

        async def _wrapped(**kwargs: Any) -> dict[str, Any]:
            from jobpilot_agent.api.schemas import UserContext as _UC

            ctx = JDContext(
                request_id=kwargs.get("request_id", "tool_call"),
                user_id=kwargs.get("user_id", "unknown"),
                jd_text=kwargs["jd_text"],
                user_context=kwargs.get("user_context") or _UC(),
            )
            output = await skill_ref.invoke(ctx)
            return output.model_dump()

        return StructuredTool.from_function(
            coroutine=_wrapped,
            name=self.metadata.name,
            description=full_description,
            args_schema=self.input_schema,
        )

    # ===== 便捷属性 =====

    @property
    def name(self) -> str:
        """Skill 唯一名称，来自 metadata.name。"""
        return self.metadata.name

    def __repr__(self) -> str:
        return f"<Skill name={self.name!r} version={self.metadata.version!r}>"

    # ===== 内部工具 =====

    @staticmethod
    def _measure_ms(start: float) -> int:
        """从 time.monotonic() 计时点计算耗时毫秒。"""
        return int((time.monotonic() - start) * 1000)
