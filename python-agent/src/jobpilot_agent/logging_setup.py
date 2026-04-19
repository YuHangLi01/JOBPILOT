"""
结构化日志配置

- 开发环境（app_env == "dev"）：structlog ConsoleRenderer，带颜色的可读格式
- 生产/预发布环境：structlog + python-json-logger，输出 JSON 便于日志采集
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from jobpilot_agent.config import Settings


def setup_logging(settings: Settings) -> None:
    """在 FastAPI lifespan 启动时调用一次。"""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.app_env == "dev":
        # 彩色可读格式
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
            cache_logger_on_first_use=True,
        )
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stderr,
            level=log_level,
        )
    else:
        # JSON 格式（生产）
        structlog.configure(
            processors=[
                *shared_processors,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(log_level),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
            cache_logger_on_first_use=True,
        )
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stdout,
            level=log_level,
        )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """获取绑定了 logger name 的 structlog 实例。"""
    return structlog.get_logger(name)  # type: ignore[return-value]


def bind_request_context(
    request_id: str,
    user_id: str | None = None,
    thread_id: str | None = None,
) -> None:
    """
    将请求上下文绑定到当前 contextvars。
    在中间件中调用，后续同一请求的所有日志自动携带这些字段。
    """
    ctx: dict[str, str] = {"request_id": request_id}
    if user_id is not None:
        ctx["user_id"] = user_id
    if thread_id is not None:
        ctx["thread_id"] = thread_id
    structlog.contextvars.bind_contextvars(**ctx)


def clear_request_context() -> None:
    """请求结束后清理 contextvars，防止跨请求污染。"""
    structlog.contextvars.clear_contextvars()
