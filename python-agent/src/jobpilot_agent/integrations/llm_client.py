"""统一 LLM 客户端。

封装 langchain_openai.ChatOpenAI，统一读取配置，提供：
- `get_llm()` / `get_lite_llm()`：原有工厂（兼容旧调用）
- `LLMClient.chat_json()`：带 JSON mode + Pydantic 校验 + tenacity 重试的高级接口
- `get_llm_client()`：进程级单例工厂，供 Skill 调用

设计说明：
- 所有 Skill 通过 `get_llm_client()` 而非直接实例化 ChatOpenAI
- JSON mode 通过 `model_kwargs={"response_format": {"type": "json_object"}}` 触发
- token 使用量从 response.response_metadata["token_usage"] 读取
- 重试仅覆盖 JSON 解析失败和 LLM 临时错误；ValidationError 不重试
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Optional, Type

from pydantic import BaseModel, ValidationError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

from jobpilot_agent.config import get_settings
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Token 使用量追踪
# ---------------------------------------------------------------------------


class TokenUsage(BaseModel):
    """LLM 调用的 token 使用量（含重试累加）。

    Attributes:
        prompt_tokens: 输入 token 数。
        completion_tokens: 输出 token 数。
        total_tokens: 合计（prompt + completion）。
        call_count: 实际调用次数（含重试）。
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 1


# ---------------------------------------------------------------------------
# LLMClient — 高级接口
# ---------------------------------------------------------------------------


class LLMClient:
    """带 JSON mode / Pydantic 校验 / tenacity 重试的 LLM 客户端。

    不应直接实例化，通过 `get_llm_client()` 获取进程级单例。

    Example:
        >>> client = get_llm_client()
        >>> result, usage = await client.chat_json(
        ...     system="只输出 JSON",
        ...     user="分析这个 JD：...",
        ...     schema=MySchema,
        ... )
        >>> print(result.field_a, usage.total_tokens)
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def chat_json(
        self,
        system: str,
        user: str,
        schema: Optional[Type[BaseModel]] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2000,
        timeout: float = 15.0,
        max_retries: int = 2,
    ) -> tuple[BaseModel | dict[str, Any], TokenUsage]:
        """以 JSON mode 调用 LLM，可选 Pydantic 输出校验。

        Args:
            system: System prompt 文本。
            user: User prompt 文本（包含 few-shot 与实际输入）。
            schema: 期望的 Pydantic 输出 Schema；为 None 时直接返回 dict。
            model: 使用的模型名；None 时取 settings.llm_model。
            temperature: 采样温度，默认 0.0（确定性输出）。
            max_tokens: 最大输出 token 数。
            timeout: 单次调用超时（秒），不含重试等待时间。
            max_retries: JSON 解析或 LLM 错误时的最大重试次数。

        Returns:
            Tuple of (parsed_result, token_usage):
            - parsed_result: schema.model_validate(…) 的实例，或 raw dict
            - token_usage: 含 call_count 的累计 token 使用量

        Raises:
            ValidationError: schema 不为 None 且 JSON 解析后不符合 schema（重试耗尽后）。
            Exception: LLM 调用彻底失败（重试耗尽后）。
        """
        usage = TokenUsage()
        _model = model or self._settings.llm_model

        async def _single_call() -> BaseModel | dict[str, Any]:
            """单次调用（被 tenacity 包裹重试）。"""
            from langchain_core.messages import HumanMessage, SystemMessage
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(
                base_url=self._settings.llm_api_base_url,
                api_key=self._settings.llm_api_key,  # type: ignore[arg-type]
                model=_model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                model_kwargs={"response_format": {"type": "json_object"}},
            )

            messages = [
                SystemMessage(content=system),
                HumanMessage(content=user),
            ]

            response = await llm.ainvoke(messages)

            # 累计 token
            meta = getattr(response, "response_metadata", {}) or {}
            tu = meta.get("token_usage") or {}
            usage.prompt_tokens += int(tu.get("prompt_tokens", 0))
            usage.completion_tokens += int(tu.get("completion_tokens", 0))
            usage.total_tokens += int(
                tu.get("total_tokens", usage.prompt_tokens + usage.completion_tokens)
            )

            raw_content: str = response.content  # type: ignore[assignment]

            # JSON 解析
            try:
                raw_dict = json.loads(raw_content)
            except json.JSONDecodeError as exc:
                log.warning(
                    "llm_client.chat_json.json_decode_error",
                    model=_model,
                    error=str(exc),
                    raw=raw_content[:200],
                )
                raise

            if schema is not None:
                return schema.model_validate(raw_dict)
            return raw_dict

        # tenacity 重试：只重试 JSON 解析失败；ValidationError 不重试（schema 问题）
        @retry(
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type(json.JSONDecodeError),
            reraise=True,
        )
        async def _with_retry() -> BaseModel | dict[str, Any]:
            nonlocal usage
            if usage.call_count > 1:
                log.info(
                    "llm_client.chat_json.retry",
                    model=_model,
                    call_count=usage.call_count,
                )
            result = await _single_call()
            return result

        # 在首次调用前 call_count=1，每次重试 before 钩子里增加
        # 使用 tenacity before_sleep 计数
        @retry(
            stop=stop_after_attempt(max_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
            retry=retry_if_exception_type(json.JSONDecodeError),
            reraise=True,
            before_sleep=lambda retry_state: setattr(  # type: ignore[func-returns-value]
                usage, "call_count", (retry_state.attempt_number + 1)
            ),
        )
        async def _with_retry_counted() -> BaseModel | dict[str, Any]:
            return await _single_call()

        result = await _with_retry_counted()
        log.debug(
            "llm_client.chat_json.done",
            model=_model,
            total_tokens=usage.total_tokens,
            call_count=usage.call_count,
        )
        return result, usage


# ---------------------------------------------------------------------------
# 原有工厂（兼容旧调用）
# ---------------------------------------------------------------------------


@lru_cache
def get_llm() -> "ChatOpenAI":
    """返回主力模型实例（doubao-pro-4k 或配置中的 llm_model）。"""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    log.debug("llm_client.get_llm", model=settings.llm_model)
    return ChatOpenAI(
        base_url=settings.llm_api_base_url,
        api_key=settings.llm_api_key,  # type: ignore[arg-type]
        model=settings.llm_model,
        temperature=0.7,
    )


@lru_cache
def get_lite_llm() -> "ChatOpenAI":
    """返回轻量模型实例（doubao-lite-4k，用于快速评估或低成本场景）。"""
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    log.debug("llm_client.get_lite_llm", model=settings.llm_model_lite)
    return ChatOpenAI(
        base_url=settings.llm_api_base_url,
        api_key=settings.llm_api_key,  # type: ignore[arg-type]
        model=settings.llm_model_lite,
        temperature=0.3,
    )


# ---------------------------------------------------------------------------
# 新版单例工厂
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    """返回 LLMClient 进程级单例。

    所有 Skill 应通过此函数获取客户端实例，不得直接实例化 LLMClient 或 ChatOpenAI。

    Returns:
        LLMClient 单例。
    """
    log.info("llm_client.initialized")
    return LLMClient()
