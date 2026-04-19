"""测试 retrieval/rrf_ranker.py — RRFRanker 公式正确性。

每个 test case 都手工推导期望 RRF 分，验证实现与公式一致。
RRF 公式：score(d) = Σ 1/(k + rank_i(d))
"""

import pytest

from jobpilot_agent.retrieval.rrf_ranker import RRFRanker
from jobpilot_agent.retrieval.types import RetrievalResult


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------


def make_result(
    doc_id: str,
    score: float,
    dense_score: float | None = None,
    sparse_score: float | None = None,
    rank_dense: int | None = None,
    rank_sparse: int | None = None,
) -> RetrievalResult:
    return RetrievalResult(
        doc_id=doc_id,
        text=f"text of {doc_id}",
        metadata={"id": doc_id},
        score=score,
        dense_score=dense_score,
        sparse_score=sparse_score,
        rank_in_dense=rank_dense,
        rank_in_sparse=rank_sparse,
    )


# ---------------------------------------------------------------------------
# 基础 RRF 公式验证（k=60）
# ---------------------------------------------------------------------------


def test_rrf_formula_doc_in_both() -> None:
    """doc_A 在 dense rank=1 和 sparse rank=1，期望分 = 1/61 + 1/61 ≈ 0.032787。"""
    k = 60
    ranker = RRFRanker(k=k)
    dense = [make_result("doc_A", 0.9, dense_score=0.9, rank_dense=1)]
    sparse = [make_result("doc_A", 1.5, sparse_score=1.5, rank_sparse=1)]
    results = ranker.rank(dense, sparse, top_k=1)

    assert len(results) == 1
    expected = 1.0 / (k + 1) + 1.0 / (k + 1)
    assert abs(results[0].score - expected) < 1e-9


def test_rrf_formula_doc_only_in_dense() -> None:
    """doc_B 只在 dense 中（rank=1），sparse 无。
    absent sparse rank = len(sparse) + 1 = 1（sparse 有 1 条其他文档）。
    期望分 = 1/(60+1) + 1/(60+2) = 1/61 + 1/62。
    """
    k = 60
    ranker = RRFRanker(k=k)
    dense = [make_result("doc_B", 0.8, dense_score=0.8, rank_dense=1)]
    sparse = [make_result("doc_C", 1.0, sparse_score=1.0, rank_sparse=1)]  # 不同文档
    results = ranker.rank(dense, sparse, top_k=5)

    doc_b = next(r for r in results if r.doc_id == "doc_B")
    # absent sparse rank for doc_B = 1 + 1 = 2
    expected = 1.0 / (k + 1) + 1.0 / (k + 2)
    assert abs(doc_b.score - expected) < 1e-9


def test_rrf_both_lists_empty_returns_empty() -> None:
    ranker = RRFRanker()
    assert ranker.rank([], [], top_k=5) == []


def test_rrf_dense_only() -> None:
    ranker = RRFRanker()
    dense = [make_result(f"d{i}", 0.9 - i * 0.1, rank_dense=i + 1) for i in range(3)]
    results = ranker.rank(dense, [], top_k=3)
    assert len(results) == 3
    # 第 1 名分数最高
    assert results[0].score >= results[1].score >= results[2].score


def test_rrf_sparse_only() -> None:
    ranker = RRFRanker()
    sparse = [make_result(f"s{i}", float(3 - i), sparse_score=float(3 - i), rank_sparse=i + 1) for i in range(3)]
    results = ranker.rank([], sparse, top_k=3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# 排名一致性
# ---------------------------------------------------------------------------


def test_rrf_higher_rank_gets_higher_score() -> None:
    """同时出现在两路中，排名越靠前分越高。"""
    k = 60
    ranker = RRFRanker(k=k)
    # doc_A: dense=1, sparse=1；doc_B: dense=2, sparse=2
    dense = [
        make_result("doc_A", 0.9, rank_dense=1),
        make_result("doc_B", 0.8, rank_dense=2),
    ]
    sparse = [
        make_result("doc_A", 2.0, rank_sparse=1),
        make_result("doc_B", 1.5, rank_sparse=2),
    ]
    results = ranker.rank(dense, sparse, top_k=2)
    assert results[0].doc_id == "doc_A"
    assert results[0].score > results[1].score


def test_rrf_top_k_truncates() -> None:
    ranker = RRFRanker()
    dense = [make_result(f"d{i}", 1.0, rank_dense=i + 1) for i in range(10)]
    sparse = [make_result(f"d{i}", 1.0, rank_sparse=i + 1) for i in range(10)]
    results = ranker.rank(dense, sparse, top_k=3)
    assert len(results) == 3


def test_rrf_preserves_original_scores() -> None:
    """融合后 dense_score / sparse_score 应保留原始值。"""
    ranker = RRFRanker()
    dense = [make_result("doc_A", 0.9, dense_score=0.9)]
    sparse = [make_result("doc_A", 1.8, sparse_score=1.8)]
    results = ranker.rank(dense, sparse, top_k=1)
    assert results[0].dense_score == 0.9
    assert results[0].sparse_score == 1.8


def test_rrf_preserves_rank_fields() -> None:
    ranker = RRFRanker()
    dense = [make_result("doc_A", 0.9, rank_dense=1)]
    sparse = [make_result("doc_A", 1.5, rank_sparse=1)]
    results = ranker.rank(dense, sparse, top_k=1)
    assert results[0].rank_in_dense == 1
    assert results[0].rank_in_sparse == 1


def test_rrf_doc_only_in_one_list_rank_fields() -> None:
    """只在 dense 中的文档，rank_in_sparse 应为 None。"""
    ranker = RRFRanker()
    dense = [make_result("doc_A", 0.9)]
    sparse = [make_result("doc_B", 1.0)]
    results = ranker.rank(dense, sparse, top_k=2)
    doc_a = next(r for r in results if r.doc_id == "doc_A")
    assert doc_a.rank_in_sparse is None


def test_rrf_invalid_k() -> None:
    with pytest.raises(ValueError):
        RRFRanker(k=0)

    with pytest.raises(ValueError):
        RRFRanker(k=-1)


def test_rrf_custom_k_affects_score() -> None:
    """k=1 时第 1 名的 RRF 分 = 1/(1+1)=0.5；k=60 时=1/61≈0.0164。"""
    doc = make_result("doc_A", 0.9)
    r_k1 = RRFRanker(k=1).rank([doc], [], top_k=1)
    r_k60 = RRFRanker(k=60).rank([doc], [], top_k=1)
    assert r_k1[0].score > r_k60[0].score


def test_rrf_union_of_both_lists() -> None:
    """输出中应包含两路的 union，而非交集。"""
    ranker = RRFRanker()
    dense = [make_result("doc_A", 0.9)]
    sparse = [make_result("doc_B", 1.5)]
    results = ranker.rank(dense, sparse, top_k=5)
    doc_ids = {r.doc_id for r in results}
    assert "doc_A" in doc_ids
    assert "doc_B" in doc_ids
