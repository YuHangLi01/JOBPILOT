"""Replay 指标计算单元测试。"""

from __future__ import annotations

import numpy as np
import pytest

from jobpilot_agent.evaluation.replay.metrics import (
    aggregate_metrics,
    compute_rank,
    cosine_similarity,
)
from jobpilot_agent.evaluation.replay.schema import ReplayResult


def _unit_vec(n: int, idx: int) -> np.ndarray:
    """第 idx 维为 1 的单位向量（L2 范数 = 1）。"""
    v = np.zeros(n, dtype=np.float32)
    v[idx] = 1.0
    return v


def test_cosine_similarity_perfect() -> None:
    """相同向量 → 相似度 = 1.0。"""
    v = _unit_vec(4, 0)
    assert cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-6)


def test_cosine_similarity_orthogonal() -> None:
    """正交向量 → 相似度 = 0.0。"""
    a = _unit_vec(4, 0)
    b = _unit_vec(4, 1)
    assert cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)


def test_cosine_similarity_opposite() -> None:
    """反向向量 → 相似度 = -1.0。"""
    a = _unit_vec(4, 0)
    b = -a.copy()
    assert cosine_similarity(a, b) == pytest.approx(-1.0, abs=1e-6)


def test_rank_computation_hit_rank1() -> None:
    """真实追问 sim >= threshold 且候选第 1 个最像 → rank=1, in_top_3=True。"""
    real = _unit_vec(4, 0)
    # 候选 0 与 real 完全一致（sim=1.0），候选 1/2 正交（sim=0.0）
    cands = [_unit_vec(4, 0), _unit_vec(4, 1), _unit_vec(4, 2)]
    rank, in_top_3, in_top_5 = compute_rank(real, cands, threshold=0.75)
    assert rank == 1
    assert in_top_3 is True
    assert in_top_5 is True


def test_rank_computation_miss() -> None:
    """所有候选与真实追问 sim < threshold → rank=99, in_top_3=False。"""
    real = _unit_vec(4, 0)
    cands = [_unit_vec(4, 1), _unit_vec(4, 2), _unit_vec(4, 3)]  # 全正交，sim=0
    rank, in_top_3, in_top_5 = compute_rank(real, cands, threshold=0.75)
    assert rank == 99
    assert in_top_3 is False
    assert in_top_5 is False


def test_rank_computation_partial() -> None:
    """第 2 个候选与真实最相似且超 threshold → rank=1（按 sim 重排后排第 1）。"""
    real = _unit_vec(8, 0)
    # 候选 0: sim=0.0（正交）; 候选 1: sim=1.0; 候选 2: sim=0.0
    cands = [_unit_vec(8, 1), _unit_vec(8, 0), _unit_vec(8, 2)]
    rank, in_top_3, in_top_5 = compute_rank(real, cands, threshold=0.75)
    assert rank == 1  # 候选[1] sim=1.0 排序后变第 1
    assert in_top_3 is True


def _make_result(
    pair_id: str = "p1",
    stage: str = "intro",
    sim: float = 0.8,
    in_top_3: bool = True,
    in_top_5: bool = True,
    error: str | None = None,
) -> ReplayResult:
    return ReplayResult(
        pair_id=pair_id,
        stage=stage,
        bot_next_question="Q" if not error else "",
        bot_top_k_questions=[],
        semantic_similarity=sim,
        rank_in_top_k=1 if in_top_3 else 99,
        in_top_3=in_top_3,
        in_top_5=in_top_5,
        latency_ms=100,
        tokens_used=0,
        error=error,
    )


def test_aggregate_metrics_rank_at_3() -> None:
    """rank@3 = in_top_3 的比例。"""
    results = [
        _make_result("p1", sim=0.9, in_top_3=True, in_top_5=True),
        _make_result("p2", sim=0.8, in_top_3=True, in_top_5=True),
        _make_result("p3", sim=0.6, in_top_3=False, in_top_5=True),
        _make_result("p4", sim=0.5, in_top_3=False, in_top_5=False),
    ]
    agg = aggregate_metrics(results)
    assert agg.total_pairs == 4
    assert agg.successful_pairs == 4
    assert agg.rank_at_3 == pytest.approx(0.5, abs=1e-6)  # 2/4
    assert agg.rank_at_5 == pytest.approx(0.75, abs=1e-6)  # 3/4
    assert agg.mean_similarity == pytest.approx(np.mean([0.9, 0.8, 0.6, 0.5]), abs=1e-6)


def test_aggregate_metrics_excludes_errors() -> None:
    """有 error 的结果不纳入成功统计。"""
    results = [
        _make_result("p1", sim=0.9, in_top_3=True),
        _make_result("p2", sim=0.0, in_top_3=False, error="LLM timeout"),
    ]
    agg = aggregate_metrics(results)
    assert agg.total_pairs == 2
    assert agg.successful_pairs == 1
    assert agg.mean_similarity == pytest.approx(0.9, abs=1e-6)


def test_aggregate_metrics_per_stage() -> None:
    """per_stage 分组计算正确。"""
    results = [
        _make_result("p1", stage="intro", sim=0.8, in_top_3=True),
        _make_result("p2", stage="intro", sim=0.6, in_top_3=False),
        _make_result("p3", stage="tech_qa", sim=0.7, in_top_3=True),
    ]
    agg = aggregate_metrics(results)
    assert "intro" in agg.per_stage
    assert "tech_qa" in agg.per_stage
    assert agg.per_stage["intro"].count == 2
    assert agg.per_stage["intro"].mean_similarity == pytest.approx(0.7, abs=1e-6)
    assert agg.per_stage["intro"].rank_at_3 == pytest.approx(0.5, abs=1e-6)
    assert agg.per_stage["tech_qa"].count == 1
