"""Checkpointer 工厂与应用生命周期管理。

两种使用模式：
1. 短生命周期（测试）：`async with get_checkpointer() as cp:`
2. 跨请求单例（FastAPI lifespan）：`await init_checkpointer()` / `get_active_checkpointer()`
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from jobpilot_agent.config import get_settings
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

_checkpointer_instance: Any = None
_checkpointer_conn: Any = None  # 持有底层连接以便 close


@asynccontextmanager
async def get_checkpointer() -> AsyncIterator[Any]:
    """返回 context-managed checkpointer，适合测试与一次性脚本。"""
    settings = get_settings()
    backend = settings.checkpointer_backend

    if backend == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        async with AsyncSqliteSaver.from_conn_string(
            settings.sqlite_checkpoint_path
        ) as saver:
            await saver.setup()
            log.info("checkpointer.sqlite.ready", path=settings.sqlite_checkpoint_path)
            yield saver

    elif backend == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(settings.postgres_url) as saver:
            await saver.setup()
            log.info("checkpointer.postgres.ready")
            yield saver

    else:
        raise ValueError(f"Unknown checkpointer backend: {backend}")


async def init_checkpointer() -> None:
    """FastAPI startup 调用，初始化全局单例。"""
    global _checkpointer_instance, _checkpointer_conn
    settings = get_settings()
    backend = settings.checkpointer_backend

    if backend == "sqlite":
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        _checkpointer_conn = await aiosqlite.connect(settings.sqlite_checkpoint_path)
        _checkpointer_instance = AsyncSqliteSaver(_checkpointer_conn)
        await _checkpointer_instance.setup()
        log.info("checkpointer.init.sqlite", path=settings.sqlite_checkpoint_path)

    elif backend == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(settings.postgres_url, open=False)
        await pool.open()
        _checkpointer_conn = pool
        _checkpointer_instance = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await _checkpointer_instance.setup()
        log.info("checkpointer.init.postgres")

    else:
        raise ValueError(f"Unknown checkpointer backend: {backend}")


async def close_checkpointer() -> None:
    """FastAPI shutdown 调用，释放底层连接。"""
    global _checkpointer_instance, _checkpointer_conn
    if _checkpointer_conn is not None:
        try:
            await _checkpointer_conn.close()
        except Exception:
            pass
        _checkpointer_conn = None
        _checkpointer_instance = None
    log.info("checkpointer.closed")


def get_active_checkpointer() -> Any:
    """供 graph.compile(checkpointer=...) 使用。须在 init_checkpointer() 之后调用。"""
    if _checkpointer_instance is None:
        raise RuntimeError("Checkpointer not initialized. Call init_checkpointer() first.")
    return _checkpointer_instance
