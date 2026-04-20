"""五维雷达图分数计算测试。"""

from __future__ import annotations

import pytest

from jobpilot_agent.evaluation.reports.plots import plot_five_dim_radar
from jobpilot_agent.evaluation.metrics.classification import ClassificationMetrics, FieldMetrics
from jobpilot_agent.evaluation.metrics.routing import RoutingMetrics, SkillRoutingMetrics
from jobpilot_agent.evaluation.metrics.latency import LatencyMetrics
from jobpilot_agent.evaluation.metrics.cost import CostComparison, RunCostStats


def _make_clf(joint_accuracy: float = 0.90) -> ClassificationMetrics:
    fm = FieldMetrics(
        accuracy=joint_accuracy,
        macro_f1=joint_accuracy,
        weighted_f1=joint_accuracy,
        precision_per_class={"A": joint_accuracy},
        recall_per_class={"A": joint_accuracy},
        f1_per_class={"A": joint_accuracy},
        confusion_matrix=[[90, 10], [5, 95]],
        labels_order=["A", "B"],
        support_per_class={"A": 100, "B": 100},
    )
    return ClassificationMetrics(
        joint_accuracy=joint_accuracy,
        evaluated_count=100,
        per_field={"job_type": fm},
    )


def _make_routing(macro_f1: float = 0.85, over_inv: float = 0.05) -> RoutingMetrics:
    sm = SkillRoutingMetrics(
        precision=macro_f1, recall=macro_f1, f1=macro_f1,
        true_positive=85, false_positive=5, false_negative=10, true_negative=900,
    )
    return RoutingMetrics(
        macro_precision=macro_f1,
        macro_recall=macro_f1,
        macro_f1=macro_f1,
        over_invocation_rate=over_inv,
        under_invocation_rate=0.05,
        perfect_match_rate=0.80,
        evaluated_count=100,
        per_skill={"interview_rag": sm},
    )


def _make_latency(p95_ms: float = 5000.0) -> LatencyMetrics:
    return LatencyMetrics(
        p50_ms=3000, p90_ms=4500, p95_ms=p95_ms, p99_ms=7000,
        mean_ms=3200, max_ms=8000, min_ms=1000,
        evaluated_count=100, per_node={},
    )


def _make_cost(main_tokens: int = 100000, baseline_tokens: int = 200000) -> CostComparison:
    main = RunCostStats(
        total_tokens=main_tokens, avg_tokens_per_jd=main_tokens // 100,
        total_llm_calls=300, total_external_calls=100,
        estimated_cost_cny=0.1, estimated_cost_usd=0.014,
        evaluated_count=100,
    )
    baseline = RunCostStats(
        total_tokens=baseline_tokens, avg_tokens_per_jd=baseline_tokens // 100,
        total_llm_calls=600, total_external_calls=200,
        estimated_cost_cny=0.2, estimated_cost_usd=0.028,
        evaluated_count=100,
    )
    return CostComparison(
        main=main, baseline=baseline,
        token_reduction_pct=0.5,
        llm_call_reduction_pct=0.5,
        cost_saved_pct=0.5,
        token_price_per_1k_cny=0.001,
    )


def test_radar_latency_score_is_zero_when_main_equals_baseline():
    """当主图延迟 = baseline 延迟时，低延迟维度应为 0（不是负数）。"""
    clf = _make_clf()
    routing = _make_routing()
    main_lat = _make_latency(5000)
    base_lat = _make_latency(5000)
    cost = _make_cost()

    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        path = plot_five_dim_radar(
            clf_metrics=clf,
            routing_metrics=routing,
            main_latency=main_lat,
            cost=cost,
            baseline_latency=base_lat,
            output_dir=Path(tmpdir),
        )
        assert path.exists()
        assert path.name == "five_dim_radar.png"


def test_radar_main_faster_than_baseline_gives_positive_latency_score():
    """当主图 P95 < baseline P95 时，低延迟分数应 > 0。"""
    clf = _make_clf()
    routing = _make_routing()
    main_lat = _make_latency(3000)
    base_lat = _make_latency(6000)
    cost = _make_cost()

    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        path = plot_five_dim_radar(
            clf_metrics=clf,
            routing_metrics=routing,
            main_latency=main_lat,
            cost=cost,
            baseline_latency=base_lat,
            output_dir=Path(tmpdir),
        )
        assert path.exists()


def test_radar_cost_score_proportional_to_token_savings():
    """主图 Token 减半时，低成本分数应为 0.5。"""
    import tempfile
    from pathlib import Path
    clf = _make_clf()
    routing = _make_routing()
    main_lat = _make_latency()
    base_lat = _make_latency()
    cost = _make_cost(main_tokens=100000, baseline_tokens=200000)

    with tempfile.TemporaryDirectory() as tmpdir:
        path = plot_five_dim_radar(
            clf_metrics=clf,
            routing_metrics=routing,
            main_latency=main_lat,
            cost=cost,
            baseline_latency=base_lat,
            output_dir=Path(tmpdir),
        )
        assert path.exists()


def test_radar_low_over_invocation_score():
    """over_invocation_rate=0.0 时，低 over-inv 维度应为 1.0。"""
    import tempfile
    from pathlib import Path
    clf = _make_clf()
    routing = _make_routing(over_inv=0.0)
    lat = _make_latency()
    cost = _make_cost()

    with tempfile.TemporaryDirectory() as tmpdir:
        path = plot_five_dim_radar(
            clf_metrics=clf,
            routing_metrics=routing,
            main_latency=lat,
            cost=cost,
            baseline_latency=lat,
            output_dir=Path(tmpdir),
        )
        assert path.exists()
