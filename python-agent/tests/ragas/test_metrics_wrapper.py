"""metrics_wrapper 单元测试。"""

from __future__ import annotations

import math

import pytest

from jobpilot_agent.evaluation.ragas.metrics_wrapper import aggregate_results, safe_float
from jobpilot_agent.evaluation.ragas.schema import RagasExample, RagasResult


# ── safe_float ────────────────────────────────────────────────────────────────


def test_safe_float_passes_normal_value():
    assert safe_float(0.75) == pytest.approx(0.75)


def test_safe_float_converts_none_to_zero():
    assert safe_float(None) == 0.0


def test_safe_float_converts_nan_to_zero():
    assert safe_float(float("nan")) == 0.0


def test_safe_float_converts_inf_to_zero():
    assert safe_float(float("inf")) == 0.0


def test_safe_float_handles_zero():
    assert safe_float(0.0) == 0.0


def test_safe_float_handles_one():
    assert safe_float(1.0) == pytest.approx(1.0)


# ── aggregate_results ─────────────────────────────────────────────────────────


def _make_example(eid: str, company: str = "A", job_type: str = "tech") -> RagasExample:
    return RagasExample(
        example_id=eid,
        jd_id=eid,
        jd_text="sample jd",
        company=company,
        position="engineer",
        job_type=job_type,
        question="q",
    )


def _make_result(eid: str, cr=0.8, cre=0.85, fai=0.9, ar=0.82, error=None) -> RagasResult:
    return RagasResult(
        example_id=eid,
        context_relevancy=cr,
        context_recall=cre,
        faithfulness=fai,
        answer_relevancy=ar,
        error=error,
    )


def test_aggregate_computes_correct_means():
    examples = [_make_example("e1"), _make_example("e2")]
    results = [
        _make_result("e1", cr=0.8, cre=0.8, fai=0.9, ar=0.8),
        _make_result("e2", cr=0.6, cre=0.9, fai=0.8, ar=0.9),
    ]
    agg = aggregate_results(results, examples)
    assert agg.mean_context_relevancy == pytest.approx(0.7, abs=1e-6)
    assert agg.mean_faithfulness == pytest.approx(0.85, abs=1e-6)
    assert agg.total == 2
    assert agg.successful == 2


def test_aggregate_excludes_error_results():
    examples = [_make_example("e1"), _make_example("e2")]
    results = [
        _make_result("e1", cr=1.0, cre=1.0, fai=1.0, ar=1.0),
        _make_result("e2", error="failed"),
    ]
    agg = aggregate_results(results, examples)
    assert agg.successful == 1
    assert agg.total == 2
    assert agg.mean_context_relevancy == pytest.approx(1.0)


def test_aggregate_by_company_groups_correctly():
    examples = [
        _make_example("e1", company="字节"),
        _make_example("e2", company="字节"),
        _make_example("e3", company="腾讯"),
    ]
    results = [
        _make_result("e1", cr=0.8),
        _make_result("e2", cr=0.6),
        _make_result("e3", cr=0.9),
    ]
    agg = aggregate_results(results, examples)
    assert "字节" in agg.by_company
    assert "腾讯" in agg.by_company
    assert agg.by_company["字节"].count == 2
    assert agg.by_company["腾讯"].count == 1


def test_aggregate_by_job_type():
    examples = [
        _make_example("e1", job_type="tech"),
        _make_example("e2", job_type="product"),
    ]
    results = [_make_result("e1"), _make_result("e2")]
    agg = aggregate_results(results, examples)
    assert "tech" in agg.by_job_type
    assert "product" in agg.by_job_type


def test_aggregate_handles_nan_values():
    examples = [_make_example("e1")]
    results = [_make_result("e1", cr=float("nan"), cre=0.9, fai=float("nan"), ar=0.8)]
    agg = aggregate_results(results, examples)
    # NaN → 0 → mean includes those zeros
    assert agg.mean_context_relevancy == pytest.approx(0.0)
    assert agg.mean_context_recall == pytest.approx(0.9)
