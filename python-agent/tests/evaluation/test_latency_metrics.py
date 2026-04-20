"""test_latency_metrics.py — 延迟指标单元测试。

验证 numpy.percentile 算法的正确性和边界行为。
"""

from __future__ import annotations

import pytest

from jobpilot_agent.evaluation.metrics.latency import compute_latency_metrics
from tests.evaluation.conftest import make_record


def _make_latency_records(latencies: list[int]) -> list:
    return [
        make_record(jd_id=f"r_{i}", latency_ms=lat)
        for i, lat in enumerate(latencies)
    ]


def test_p95_known_value():
    """100 条记录，值为 1..100，P95 应为 95.05（numpy linear interpolation）。"""
    records = _make_latency_records(list(range(1, 101)))
    metrics = compute_latency_metrics(records)
    # numpy percentile 95 of [1..100] ≈ 95.05
    assert abs(metrics.p95_ms - 95.05) < 0.5


def test_p50_known_value():
    """偶数个元素，P50（中位数）= (50+51)/2 = 50.5。"""
    records = _make_latency_records(list(range(1, 101)))
    metrics = compute_latency_metrics(records)
    assert abs(metrics.p50_ms - 50.5) < 0.1


def test_mean_known_value():
    """1..100 的均值 = 50.5。"""
    records = _make_latency_records(list(range(1, 101)))
    metrics = compute_latency_metrics(records)
    assert abs(metrics.mean_ms - 50.5) < 0.01


def test_max_ms():
    """最大值 = 100。"""
    records = _make_latency_records(list(range(1, 101)))
    metrics = compute_latency_metrics(records)
    assert metrics.max_ms == 100.0


def test_min_ms():
    """最小值 = 1。"""
    records = _make_latency_records(list(range(1, 101)))
    metrics = compute_latency_metrics(records)
    assert metrics.min_ms == 1.0


def test_evaluated_count():
    """20 条有效 + 5 条 latency=0（被过滤）→ evaluated_count = 20。"""
    valid = _make_latency_records([1000] * 20)
    zero_lat = [make_record(jd_id=f"zero_{i}", latency_ms=0) for i in range(5)]
    metrics = compute_latency_metrics(valid + zero_lat)
    assert metrics.evaluated_count == 20


def test_per_node_latency():
    """per_node 包含 parse_jd 节点，且 P95 / mean 可计算。"""
    records = [
        make_record(
            jd_id=f"r_{i}",
            latency_ms=3000,
            per_node_ms={"parse_jd": 500 + i * 10, "classify_jd": 400},
        )
        for i in range(20)
    ]
    metrics = compute_latency_metrics(records)
    assert "parse_jd" in metrics.per_node
    nl = metrics.per_node["parse_jd"]
    assert nl.p95_ms > 0
    assert nl.mean_ms > 0
    assert nl.sample_count == 20


def test_failed_records_excluded():
    """success=False 的记录不计入延迟统计。"""
    valid = _make_latency_records([2000] * 15)
    failed = [make_record(jd_id=f"fail_{i}", success=False, latency_ms=9999) for i in range(5)]
    metrics = compute_latency_metrics(valid + failed)
    assert metrics.evaluated_count == 15
    assert metrics.max_ms < 9000


def test_raises_on_no_valid_records():
    """全部失败时应抛出 ValueError。"""
    records = [make_record(jd_id=f"fail_{i}", success=False) for i in range(5)]
    with pytest.raises(ValueError, match="没有有效"):
        compute_latency_metrics(records)


def test_target_p95_under_8s():
    """所有延迟 <= 7000ms → P95 < 8000ms（满足目标）。"""
    records = _make_latency_records([5000 + i * 10 for i in range(20)])
    metrics = compute_latency_metrics(records)
    assert metrics.p95_ms < 8000
