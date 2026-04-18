"""
统一 LLM 客户端

封装 langchain_openai.ChatOpenAI，统一读取配置。
提供 get_llm() 和 get_lite_llm() 工厂函数。
当前为 stub 实现（不发起真实网络请求），待下周正式接入。
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI

from jobpilot_agent.config import get_settings
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


@lru_cache
def get_llm() -> ChatOpenAI:
    """返回主力模型实例（doubao-pro-4k 或配置中的 llm_model）。"""
    from langchain_openai import ChatOpenAI  # 延迟导入，避免启动时强制联网

    settings = get_settings()
    log.debug("llm_client.get_llm", model=settings.llm_model)
    return ChatOpenAI(
        base_url=settings.llm_api_base_url,
        api_key=settings.llm_api_key,  # type: ignore[arg-type]
        model=settings.llm_model,
        temperature=0.7,
    )


@lru_cache
def get_lite_llm() -> ChatOpenAI:
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
