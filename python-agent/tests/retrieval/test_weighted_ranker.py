"""测试 retrieval/rrf_ranker.py — WeightedRanker 归一化加权融合。"""

import pytest

from jobpilot_agent.retrieval.rrf_ranker import WeightedRanker
from jobpilot_agent.retrieval.types import RetrievalResult


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------


def make_result(
    doc_id: str,
    dense_score: float | None = None,
    sparse_score: float | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        doc_id=doc_id,
        text=f"text {doc_id}",
        metadata={},
        score=dense_score or sparse_score or 0.0,
        dense_score=dense_score,
        sparse_score=sparse_score,
    )


# ---------------------------------------------------------------------------
# 基础功能
# ---------------------------------------------------------------------------


def test_weighted_empty_both() -> None:
    ranker = WeightedRanker(dense_weight=0.7, sparse_weight=0.3)
    assert ranker.rank([], [], top_k=5) == []


def test_weighted_dense_only() -> None:
    ranker = WeightedRanker(dense_weight=1.0, sparse_weight=0.0)
    dense = [
        make_result("doc_A", dense_score=0.9),
        make_result("doc_B", dense_score=0.5),
    ]
    results = ranker.rank(dense, [], top_k=2)
    assert len(results) == 2
    assert results[0].doc_id == "doc_A"


def test_weighted_sparse_only() -> None:
    ranker = WeightedRanker(dense_weight=0.0, sparse_weight=1.0)
    sparse = [
        make_result("doc_C", sparse_score=3.0),
        make_result("doc_D", sparse_score=1.0),
    ]
    results = ranker.rank([], sparse, top_k=2)
    assert len(results) == 2
    assert results[0].doc_id == "doc_C"


# ---------------------------------------------------------------------------
# 归一化验证
# ---------------------------------------------------------------------------


def test_normalization_all_same_dense_score() -> None:
    """所有 dense_score 相同时，归一化后均为 1.0，加权结果取决于 sparse。"""
    ranker = WeightedRanker(dense_weight=0.5, sparse_weight=0.5)
    dense = [
        make_result("doc_A", dense_score=0.8),
        make_result("doc_B", dense_score=0.8),
    ]
    sparse = [
        make_result("doc_A", sparse_score=2.0),
        make_result("doc_B", sparse_score=1.0),
    ]
    results = ranker.rank(dense, sparse, top_k=2)
    # doc_A 有更高的 sparse_score，应排在前面
    assert results[0].doc_id == "doc_A"


def test_weighted_score_higher_than_zero() -> None:
    ranker = WeightedRanker(dense_weight=0.6, sparse_weight=0.4)
    dense = [make_result("doc_A", dense_score=0.9)]
    sparse = [make_result("doc_A", sparse_score=1.5)]
    results = ranker.rank(dense, sparse, top_k=1)
    assert results[0].score > 0


def test_weighted_top_k_respected() -> None:
    ranker = WeightedRanker(dense_weight=0.5, sparse_weight=0.5)
    dense = [make_result(f"d{i}", dense_score=float(10 - i)) for i in range(8)]
    sparse = [make_result(f"d{i}", sparse_score=float(10 - i)) for i in range(8)]
    results = ranker.rank(dense, sparse, top_k=3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# 原始分数保留
# ---------------------------------------------------------------------------


def test_weighted_preserves_dense_sparse_scores() -> None:
    ranker = WeightedRanker(dense_weight=0.7, sparse_weight=0.3)
    dense = [make_result("doc_A", dense_score=0.9)]
    sparse = [make_result("doc_A", sparse_score=1.5)]
    results = ranker.rank(dense, sparse, top_k=1)
    assert results[0].dense_score == 0.9
    assert results[0].sparse_score == 1.5


def test_weighted_union_of_both_lists() -> None:
    ranker = WeightedRanker(dense_weight=0.7, sparse_weight=0.3)
    dense = [make_result("doc_A", dense_score=0.9)]
    sparse = [make_result("doc_B", sparse_score=1.5)]
    results = ranker.rank(dense, sparse, top_k=5)
    ids = {r.doc_id for r in results}
    assert "doc_A" in ids
    assert "doc_B" in ids


# ---------------------------------------------------------------------------
# 异常参数
# ---------------------------------------------------------------------------


def test_weighted_negative_weight_raises() -> None:
    with pytest.raises(ValueError):
        WeightedRanker(dense_weight=-0.1, sparse_weight=0.5)


def test_weighted_both_zero_raises() -> None:
    with pytest.raises(ValueError):
        WeightedRanker(dense_weight=0.0, sparse_weight=0.0)


# ---------------------------------------------------------------------------
# 排序稳定性
# ---------------------------------------------------------------------------


def test_weighted_scores_descending() -> None:
    ranker = WeightedRanker(dense_weight=0.5, sparse_weight=0.5)
    dense = [
        make_result("doc_A", dense_score=0.9),
        make_result("doc_B", dense_score=0.5),
        make_result("doc_C", dense_score=0.2),
    ]
    sparse = [
        make_result("doc_A", sparse_score=2.0),
        make_result("doc_B", sparse_score=1.0),
        make_result("doc_C", sparse_score=0.3),
    ]
    results = ranker.rank(dense, sparse, top_k=3)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
