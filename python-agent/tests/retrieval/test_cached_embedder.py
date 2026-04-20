"""CachedEmbedder LRU 缓存单元测试。"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from jobpilot_agent.retrieval.embedding import BaseEmbedder, CachedEmbedder


class _CountingEmbedder(BaseEmbedder):
    """计数型 mock embedder：记录被调用次数及每次输入。"""

    def __init__(self, dim: int = 4) -> None:
        self._dim = dim
        self.calls: list[list[str]] = []

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        self.calls.append(list(texts))
        # 生成可区分的向量：每个文本映射为 [len, len, len, len] 做归一化
        out = np.array(
            [[len(t) + 0.1 * i] * self._dim for i, t in enumerate(texts)],
            dtype=np.float32,
        )
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norms == 0, 1.0, norms)


@pytest.mark.asyncio
async def test_cache_hit_avoids_inner_call() -> None:
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner, max_size=100)

    v1 = await cached.embed_texts(["hello"])
    v2 = await cached.embed_texts(["hello"])

    assert len(inner.calls) == 1, "第二次应完全命中缓存，不调用底层"
    assert inner.calls[0] == ["hello"]
    np.testing.assert_allclose(v1, v2)

    stats = cached.cache_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_mixed_hit_and_miss_only_forwards_misses() -> None:
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner, max_size=100)

    await cached.embed_texts(["a", "b"])  # 都是 miss
    await cached.embed_texts(["a", "c", "b"])  # 只有 c 是 miss

    assert len(inner.calls) == 2
    assert inner.calls[0] == ["a", "b"]
    assert inner.calls[1] == ["c"], "只有 miss 文本才转发给底层"


@pytest.mark.asyncio
async def test_lru_eviction_when_size_exceeded() -> None:
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner, max_size=2)

    await cached.embed_texts(["a"])
    await cached.embed_texts(["b"])
    await cached.embed_texts(["c"])  # 应淘汰 a

    await cached.embed_texts(["a"])  # a 被淘汰，应再次 miss
    assert inner.calls[-1] == ["a"]
    stats = cached.cache_stats()
    assert stats["size"] == 2


@pytest.mark.asyncio
async def test_empty_input_returns_empty_without_inner_call() -> None:
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner)

    out = await cached.embed_texts([])
    assert out.shape == (0, inner.dimension)
    assert len(inner.calls) == 0


@pytest.mark.asyncio
async def test_cache_preserves_ordering_with_mixed_results() -> None:
    """命中和未命中混合时，返回向量顺序必须与输入一致。"""
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner, max_size=100)

    await cached.embed_texts(["x", "y"])  # 预热
    out = await cached.embed_texts(["y", "z", "x"])

    # y 和 x 应从缓存取，顺序与输入一致
    cached_x = await cached.embed_texts(["x"])
    cached_y = await cached.embed_texts(["y"])
    np.testing.assert_allclose(out[0], cached_y[0])  # y 在位置 0
    np.testing.assert_allclose(out[2], cached_x[0])  # x 在位置 2


@pytest.mark.asyncio
async def test_concurrent_same_key_safe() -> None:
    """并发请求相同 key 时，缓存最终一致（允许底层被调用 >1 次）。"""
    inner = _CountingEmbedder()
    cached = CachedEmbedder(inner, max_size=100)

    results = await asyncio.gather(
        *[cached.embed_texts(["concurrent"]) for _ in range(5)]
    )
    # 所有结果应一致（底层对相同输入返回相同值）
    for r in results[1:]:
        np.testing.assert_allclose(r, results[0])


@pytest.mark.asyncio
async def test_aclose_delegates_to_inner_when_available() -> None:
    """CachedEmbedder.aclose 应转发给内部 embedder（若实现了）。"""
    calls: list[str] = []

    class _ClosableEmbedder(_CountingEmbedder):
        async def aclose(self) -> None:
            calls.append("closed")

    cached = CachedEmbedder(_ClosableEmbedder())
    await cached.aclose()
    assert calls == ["closed"]


@pytest.mark.asyncio
async def test_aclose_no_op_when_inner_has_no_close() -> None:
    """内部 embedder 没有 aclose 时不应抛错。"""
    cached = CachedEmbedder(_CountingEmbedder())
    await cached.aclose()  # 不抛异常即通过
