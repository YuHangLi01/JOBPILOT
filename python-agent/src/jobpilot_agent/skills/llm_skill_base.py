"""LLMSkillBase — 封装 LLM Skill 公共 invoke 错误处理模板。

所有纯 LLM Skill 继承此类，只需实现：
  - metadata (ClassVar[SkillMetadata])
  - should_invoke(ctx) -> bool
  - _run_llm(ctx) -> tuple[BaseModel, TokenUsage]

invoke 的超时处理、ValidationError 捕获、通用异常捕获、metrics 填充
均由 LLMSkillBase 统一处理，子类无需重复编写样板代码。

设计约束（同 Skill 基类）：
- invoke 绝不抛原生异常
- should_invoke 必须是纯函数（不调 LLM、无 I/O）
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ValidationError

from jobpilot_agent.integrations.llm_client import TokenUsage
from jobpilot_agent.logging_setup import get_logger
from jobpilot_agent.skills.base import Skill, SkillOutput
from jobpilot_agent.skills.context import JDContext

log = get_logger(__name__)


class LLMSkillBase(Skill, ABC):
    """LLM-only Skill 的公共基类，封装统一的 invoke 错误处理流程。

    子类只需实现 `_run_llm`，invoke 的超时 / 校验 / 兜底异常处理均由此类提供。

    Example:
        >>> class MyLLMSkill(LLMSkillBase):
        ...     metadata = SkillMetadata(name="my_llm_skill", ...)
        ...     def should_invoke(self, ctx):
        ...         return True
        ...     async def _run_llm(self, ctx):
        ...         data, usage = await get_llm_client().chat_json(
        ...             system="...", user=ctx.jd_text, schema=MySchema)
        ...         return data, usage
    """

    @abstractmethod
    async def _run_llm(self, ctx: JDContext) -> tuple[BaseModel, TokenUsage]:
        """子类实现核心 LLM 调用逻辑。

        Args:
            ctx: 当前请求的 JD 上下文。

        Returns:
            Tuple of (pydantic_result, token_usage):
            - pydantic_result: 经 schema 校验的 Pydantic 模型实例
            - token_usage: 含 call_count 的 token 使用量统计

        Raises:
            asyncio.TimeoutError: 由 invoke 层捕获，不应在此方法内处理。
            ValidationError: 由 invoke 层捕获，不应在此方法内处理。
            Exception: 其他异常由 invoke 层兜底捕获。
        """
        ...

    async def invoke(self, ctx: JDContext) -> SkillOutput:
        """执行 Skill，封装超时 / ValidationError / 通用异常处理。

        成功时：SkillOutput(success=True, data=result.model_dump(), tokens_used=...)
        超时时：SkillOutput(success=False, error="SKILL_TIMEOUT: ...")
        schema 校验失败时：SkillOutput(success=False, error="SKILL_LLM_FAIL: ...")
        其他异常：SkillOutput(success=False, error="SKILL_ERROR: ...")

        所有路径均填充 latency_ms，永远不向调用方抛原生异常。
        """
        start = time.monotonic()
        skill_name = self.metadata.name

        try:
            result, usage = await asyncio.wait_for(
                self._run_llm(ctx),
                timeout=float(ctx.timeout_seconds),
            )
            latency_ms = self._measure_ms(start)
            log.info(
                "llm_skill.invoke.success",
                skill=skill_name,
                latency_ms=latency_ms,
                tokens=usage.total_tokens,
                calls=usage.call_count,
            )
            return SkillOutput(
                skill_name=skill_name,
                success=True,
                data=result.model_dump(),
                latency_ms=latency_ms,
                tokens_used=usage.total_tokens,
                llm_calls=usage.call_count,
            )

        except asyncio.TimeoutError:
            latency_ms = self._measure_ms(start)
            log.warning(
                "llm_skill.invoke.timeout",
                skill=skill_name,
                timeout_s=ctx.timeout_seconds,
                latency_ms=latency_ms,
            )
            return SkillOutput(
                skill_name=skill_name,
                success=False,
                error=f"SKILL_TIMEOUT: exceeded {ctx.timeout_seconds}s",
                latency_ms=latency_ms,
            )

        except ValidationError as exc:
            latency_ms = self._measure_ms(start)
            log.error(
                "llm_skill.invoke.validation_error",
                skill=skill_name,
                error=str(exc),
                latency_ms=latency_ms,
            )
            return SkillOutput(
                skill_name=skill_name,
                success=False,
                error=f"SKILL_LLM_FAIL: {exc}",
                latency_ms=latency_ms,
            )

        except Exception as exc:  # noqa: BLE001
            latency_ms = self._measure_ms(start)
            log.exception(
                "llm_skill.invoke.error",
                skill=skill_name,
                exc_type=type(exc).__name__,
                error=str(exc),
                latency_ms=latency_ms,
            )
            return SkillOutput(
                skill_name=skill_name,
                success=False,
                error=f"SKILL_ERROR: {type(exc).__name__}: {exc}",
                latency_ms=latency_ms,
            )
