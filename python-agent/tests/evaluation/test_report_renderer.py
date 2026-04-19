"""test_report_renderer.py — 报告生成 smoke test。

验证报告包含 6 大章节标题，以及摘要表格中的关键字段。
不做实际 LLM 调用，使用全 mock 数据。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from jobpilot_agent.evaluation.metrics.classification import compute_classification_metrics
from jobpilot_agent.evaluation.metrics.cost import compute_cost_comparison
from jobpilot_agent.evaluation.metrics.latency import compute_latency_metrics
from jobpilot_agent.evaluation.metrics.routing import compute_routing_metrics
from jobpilot_agent.evaluation.reports.renderer import generate_report
from tests.evaluation.conftest import make_record

_ALL_SKILLS = [
    "tech_stack_extract", "gpa_check", "en_translate",
    "interview_rag", "portfolio_check", "github_scan",
]

_REQUIRED_SECTIONS = [
    "## 摘要",
    "## 1. JD 分类",
    "## 2. Skill 路由",
    "## 3. 延迟",
    "## 4. 成本",
    "## 5. 综合雷达图",
    "## 6. 错误分析",
]


def _make_dataset(n: int = 20) -> list:
    return [
        make_record(
            jd_id=f"r_{i}",
            invoked_skills=["tech_stack_extract", "interview_rag"],
            expected_skills=["tech_stack_extract", "interview_rag"],
            forbidden_skills=["gpa_check", "en_translate"],
            latency_ms=3000 + i * 50,
        )
        for i in range(n)
    ]


def test_report_contains_all_sections():
    """生成报告应包含所有 6 大章节标题。"""
    records = _make_dataset()
    base_records = [make_record(jd_id=f"base_{i}", total_tokens=3000, latency_ms=12000) for i in range(20)]

    clf = compute_classification_metrics(records)
    routing = compute_routing_metrics(records, _ALL_SKILLS)
    main_lat = compute_latency_metrics(records)
    base_lat = compute_latency_metrics(base_records)
    cost = compute_cost_comparison(records, base_records)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "scenario_a_test.md"
        report = generate_report(
            clf_metrics=clf,
            routing_metrics=routing,
            main_latency=main_lat,
            baseline_latency=base_lat,
            cost=cost,
            main_records=records,
            baseline_records=base_records,
            output_path=output_path,
        )

    for section in _REQUIRED_SECTIONS:
        assert section in report, f"报告缺少章节：{section}"


def test_report_written_to_file():
    """生成报告应写入指定文件路径。"""
    records = _make_dataset(10)
    base_records = [make_record(jd_id=f"b_{i}", total_tokens=2000, latency_ms=10000) for i in range(10)]

    clf = compute_classification_metrics(records)
    routing = compute_routing_metrics(records, _ALL_SKILLS)
    main_lat = compute_latency_metrics(records)
    base_lat = compute_latency_metrics(base_records)
    cost = compute_cost_comparison(records, base_records)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "reports" / "test.md"
        generate_report(
            clf_metrics=clf,
            routing_metrics=routing,
            main_latency=main_lat,
            baseline_latency=base_lat,
            cost=cost,
            main_records=records,
            baseline_records=base_records,
            output_path=output_path,
        )
        assert output_path.exists()
        content = output_path.read_text(encoding="utf-8")
        assert len(content) > 500


def test_report_summary_table_has_metrics():
    """摘要表格应包含 joint accuracy 和 Token 降幅两行。"""
    records = _make_dataset(10)
    base_records = [make_record(jd_id=f"b_{i}", total_tokens=2000, latency_ms=8000) for i in range(10)]

    clf = compute_classification_metrics(records)
    routing = compute_routing_metrics(records, _ALL_SKILLS)
    main_lat = compute_latency_metrics(records)
    base_lat = compute_latency_metrics(base_records)
    cost = compute_cost_comparison(records, base_records)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.md"
        report = generate_report(
            clf_metrics=clf,
            routing_metrics=routing,
            main_latency=main_lat,
            baseline_latency=base_lat,
            cost=cost,
            main_records=records,
            baseline_records=base_records,
            output_path=output_path,
        )

    assert "joint accuracy" in report
    assert "Token 降幅" in report


def test_report_bad_cases_section():
    """当有 over-invocation 记录时，报告应包含 'Over-invocation' 关键字。"""
    # 5 条有 over-invocation（调用了 forbidden skill）
    records = [
        make_record(
            jd_id=f"over_{i}",
            invoked_skills=["tech_stack_extract", "gpa_check"],
            expected_skills=["tech_stack_extract"],
            forbidden_skills=["gpa_check"],
        )
        for i in range(5)
    ] + [make_record(jd_id=f"ok_{i}") for i in range(5)]

    base_records = [make_record(jd_id=f"b_{i}", total_tokens=2000, latency_ms=8000) for i in range(10)]

    clf = compute_classification_metrics(records)
    routing = compute_routing_metrics(records, _ALL_SKILLS)
    main_lat = compute_latency_metrics(records)
    base_lat = compute_latency_metrics(base_records)
    cost = compute_cost_comparison(records, base_records)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.md"
        report = generate_report(
            clf_metrics=clf,
            routing_metrics=routing,
            main_latency=main_lat,
            baseline_latency=base_lat,
            cost=cost,
            main_records=records,
            baseline_records=base_records,
            output_path=output_path,
        )

    assert "Over-invocation" in report


def test_report_model_name_appears():
    """报告头部应包含指定的模型名称。"""
    records = _make_dataset(10)
    base_records = [make_record(jd_id=f"b_{i}", total_tokens=2000, latency_ms=8000) for i in range(10)]

    clf = compute_classification_metrics(records)
    routing = compute_routing_metrics(records, _ALL_SKILLS)
    main_lat = compute_latency_metrics(records)
    base_lat = compute_latency_metrics(base_records)
    cost = compute_cost_comparison(records, base_records)

    model_name = "doubao-pro-test-model"
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "report.md"
        report = generate_report(
            clf_metrics=clf,
            routing_metrics=routing,
            main_latency=main_lat,
            baseline_latency=base_lat,
            cost=cost,
            main_records=records,
            baseline_records=base_records,
            output_path=output_path,
            model_name=model_name,
        )

    assert model_name in report
