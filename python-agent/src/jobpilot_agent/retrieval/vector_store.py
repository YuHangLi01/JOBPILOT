"""Milvus 向量库封装（stub）。"""

from __future__ import annotations

from typing import Any

# type: ignore


async def similarity_search(
    collection: str,  # noqa: ARG001
    query_vector: list[float],  # noqa: ARG001
    top_k: int = 5,  # noqa: ARG001
) -> list[dict[str, Any]]:
    """向量相似度检索（stub）。"""
    raise NotImplementedError("vector_store is not yet implemented")
