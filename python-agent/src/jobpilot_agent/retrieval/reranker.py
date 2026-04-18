"""重排序器（stub）。"""

from __future__ import annotations

from typing import Any

# type: ignore


async def rerank(
    query: str,  # noqa: ARG001
    candidates: list[dict[str, Any]],  # noqa: ARG001
    top_k: int = 3,  # noqa: ARG001
) -> list[dict[str, Any]]:
    """对候选结果重排序（stub）。"""
    raise NotImplementedError("reranker is not yet implemented")
