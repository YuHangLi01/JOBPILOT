"""BM25 稀疏检索（stub）。"""

from __future__ import annotations

from typing import Any

# type: ignore


async def bm25_search(
    corpus: list[str],  # noqa: ARG001
    query: str,  # noqa: ARG001
    top_k: int = 5,  # noqa: ARG001
) -> list[dict[str, Any]]:
    """BM25 关键词检索（stub）。"""
    raise NotImplementedError("bm25 is not yet implemented")
