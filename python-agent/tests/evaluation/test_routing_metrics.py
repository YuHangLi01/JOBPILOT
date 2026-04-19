"""test_routing_metrics.py — Skill 路由指标单元测试。

覆盖边界条件：
- over-invocation（调用了 forbidden）
- under-invocation（漏调 expected）
- perfect match
- per-skill TP/FP/FN/TN 计数
"""

from __future__ import annotations

import pytest

from jobpilot_agent.evaluation.metrics.routing import compute_routing_metrics
from tests.evaluation.conftest import make_record

_ALL_SKILLS = [
    "tech_stack_extract", "gpa_check", "en_translate",
    "interview_rag", "portfolio_check", "github_scan",
]


def test_over_invocation_rate_zero():
    """没有调用 forbidden skill → over_invocation_rate = 0。"""
    records = [
        make_record(
            jd_id=f"r_{i}",
            invoked_skills=["tech_stack_extract", "interview_rag"],
            expected_skills=["tech_stack_extract", "interview_rag"],
            forbidden_skills=["gpa_check", "en_translate"],
        )
        for i in range(10)
    ]
    metrics = compute_routing_metrics(records, _ALL_SKILLS)
    assert metrics.over_invocation_rate == 0.0


def test_over_invocation_rate_half():
    """5/10 条调用了 forbidden skill → over_invocation_rate = 0.5。"""
    records = []
    for i in range(5):
        records.append(make_record(
            jd_id=f"ok_{i}",
            invoked_skills=["tech_stack_extract"],
            expected_skills=["tech_stack_extract"],
            forbidden_skills=["gpa_check"],
        ))
    for i in range(5):
        records.append(make_record(
            jd_id=f"over_{i}",
            invoked_skills=["tech_stack_extract", "gpa_check"],  # gpa_check is forbidden
            expected_skills=["tech_stack_extract"],
            forbidden_skills=["gpa_check"],
        ))
    metrics = compute_routing_metrics(records, _ALL_SKILLS)
    assert abs(metrics.over_invocation_rate - 0.5) < 1e-6


def test_under_invocation_rate():
    """5 条漏调 expected skill → under_invocation_rate = 0.5。"""
    records = []
    for i in range(5):
        records.append(make_record(
            jd_id=f"ok_{i}",
            invoked_skills=["tech_stack_extract", "interview_rag"],
            expected_skills=["tech_stack_extract", "interview_rag"],
            forbidden_skills=[],
        ))
    for i in range(5):
        records.append(make_record(
            jd_id=f"under_{i}",
            invoked_skills=["tech_stack_extract"],  # missing interview_rag
            expected_skills=["tech_stack_extract", "interview_rag"],
            forbidden_skills=[],
        ))
    metrics = compute_routing_metrics(records, _ALL_SKILLS)
    assert abs(metrics.under_invocation_rate - 0.5) < 1e-6


def test_perfect_match_rate():
    """全部完全匹配 → perfect_match_rate = 1.0。"""
    records = [
        make_record(
            jd_id=f"r_{i}",
            invoked_skills=["tech_stack_extract", "interview_rag"],
            expected_skills=["tech_stack_extract", "interview_rag"],
            forbidden_skills=["gpa_check"],
        )
        for i in range(10)
    ]
    metrics = compute_routing_metrics(records, _ALL_SKILLS)
    assert abs(metrics.perfect_match_rate - 1.0) < 1e-6


def test_per_skill_tp_count():
    """tech_stack_extract 被正确调用 10 次 → TP = 10。"""
    records = [
        make_record(
            jd_id=f"r_{i}",
            invoked_skills=["tech_stack_extract"],
            expected_skills=["tech_stack_extract"],
            forbidden_skills=["gpa_check"],
        )
        for i in range(10)
    ]
    metrics = compute_routing_metrics(records, _ALL_SKILLS)
    sm = metrics.per_skill["tech_stack_extract"]
    assert sm.true_positive == 10
    assert sm.false_negative == 0
    assert abs(sm.precision - 1.0) < 1e-6
    assert abs(sm.recall - 1.0) < 1e-6


def test_per_skill_fp_count():
    """gpa_check 被调用但属于 forbidden → FP = 10。"""
    records = [
        make_record(
            jd_id=f"r_{i}",
            invoked_skills=["tech_stack_extract", "gpa_check"],
            expected_skills=["tech_stack_extract"],
            forbidden_skills=["gpa_check"],
        )
        for i in range(10)
    ]
    metrics = compute_routing_metrics(records, _ALL_SKILLS)
    sm = metrics.per_skill["gpa_check"]
    assert sm.false_positive == 10
    assert sm.true_positive == 0
    assert sm.precision == 0.0


def test_per_skill_fn_count():
    """interview_rag 应调但未调 → FN = 10。"""
    records = [
        make_record(
            jd_id=f"r_{i}",
            invoked_skills=["tech_stack_extract"],
            expected_skills=["tech_stack_extract", "interview_rag"],
            forbidden_skills=["gpa_check"],
        )
        for i in range(10)
    ]
    metrics = compute_routing_metrics(records, _ALL_SKILLS)
    sm = metrics.per_skill["interview_rag"]
    assert sm.false_negative == 10
    assert sm.recall == 0.0


def test_raises_on_all_failed():
    """所有记录失败时应抛出 ValueError。"""
    records = [make_record(jd_id=f"fail_{i}", success=False) for i in range(5)]
    with pytest.raises(ValueError, match="没有有效"):
        compute_routing_metrics(records, _ALL_SKILLS)


def test_all_skills_baseline_over_invocation():
    """baseline 场景：invoked=all_skills，forbidden 非空 → over_invocation = 1.0。"""
    records = [
        make_record(
            jd_id=f"r_{i}",
            invoked_skills=_ALL_SKILLS,
            expected_skills=["tech_stack_extract"],
            forbidden_skills=["gpa_check", "en_translate"],
        )
        for i in range(10)
    ]
    metrics = compute_routing_metrics(records, _ALL_SKILLS)
    assert abs(metrics.over_invocation_rate - 1.0) < 1e-6


def test_macro_f1_all_correct():
    """所有 expected 都被正确调用，无 FP/FN → macro_f1 = 1.0。"""
    records = [
        make_record(
            jd_id=f"r_{i}",
            invoked_skills=["tech_stack_extract", "interview_rag"],
            expected_skills=["tech_stack_extract", "interview_rag"],
            forbidden_skills=["gpa_check"],
        )
        for i in range(10)
    ]
    metrics = compute_routing_metrics(records, _ALL_SKILLS)
    # F1 应接近 1.0（考虑 TN 只的 Skill 不计入 macro）
    assert metrics.macro_f1 > 0.9
