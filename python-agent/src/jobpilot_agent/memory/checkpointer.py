"""LangGraph Checkpointer（PostgreSQL，stub）。"""

from __future__ import annotations

# type: ignore


def get_checkpointer() -> None:  # type: ignore[return]
    """
    返回 langgraph-checkpoint-postgres 的 AsyncPostgresSaver 实例（stub）。
    实际使用时需传入 postgres_url 并调用 .setup() 初始化表结构。
    """
    raise NotImplementedError("checkpointer is not yet implemented")
