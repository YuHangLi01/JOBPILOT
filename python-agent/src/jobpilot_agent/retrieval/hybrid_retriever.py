"""混合检索器（向量 + BM25 融合，stub）。"""

from __future__ import annotations

from typing import Any

# type: ignore


async def hybrid_search(
    query: str,  # noqa: ARG001
    top_k: int = 5,  # noqa: ARG001
) -> list[dict[str, Any]]:
    """向量检索与 BM25 检索结果融合（stub）。"""
    raise NotImplementedError("hybrid_retriever is not yet implemented")
