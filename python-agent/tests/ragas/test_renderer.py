"""renderer smoke test — 给定固定数据，验证 Markdown 报告结构正确。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from jobpilot_agent.evaluation.ragas.renderer import render
from jobpilot_agent.evaluation.ragas.schema import RagasExample, RagasResult


def _make_example(eid: str, company: str = "字节跳动", job_type: str = "tech") -> RagasExample:
    return RagasExample(
        example_id=eid,
        jd_id=eid,
        jd_text="岗位职责：负责前端研发",
        company=company,
        position="高级前端工程师",
        job_type=job_type,
        question="针对字节跳动的高级前端工程师岗位，面试中可能会问哪些问题？",
        contexts=["React 面试题：描述虚拟 DOM 的工作原理"],
        answer="问题：请描述 React 虚拟 DOM 工作原理\n  - 通过 diff 算法减少真实 DOM 操作",
        ground_truth="React 虚拟 DOM 使用 diff 算法，最小化真实 DOM 操作次数",
        ground_truth_source="llm_assisted",
    )


def _make_result(eid: str, cr=0.8, cre=0.85, fai=0.9, ar=0.82) -> RagasResult:
    return RagasResult(
        example_id=eid,
        context_relevancy=cr,
        context_recall=cre,
        faithfulness=fai,
        answer_relevancy=ar,
    )


def test_render_creates_markdown_file():
    examples = [_make_example(f"e{i}", company=["字节", "腾讯", "阿里"][i % 3]) for i in range(5)]
    results = [_make_result(f"e{i}") for i in range(5)]

    with tempfile.TemporaryDirectory() as tmpdir:
        output = str(Path(tmpdir) / "ragas_v1.md")
        agg = render(examples, results, output)

        md = Path(output).read_text(encoding="utf-8")
        assert "RAGAS" in md
        assert "摘要" in md
        assert "Context Relevance" in md
        assert "Context Recall" in md
        assert "Faithfulness" in md
        assert "Answer Relevancy" in md
        assert "分公司表现" in md
        assert "失败案例分析" in md
        assert "结论" in md


def test_render_returns_correct_aggregate():
    examples = [_make_example("e1")]
    results = [_make_result("e1", cr=0.9, cre=0.95, fai=0.88, ar=0.85)]

    with tempfile.TemporaryDirectory() as tmpdir:
        output = str(Path(tmpdir) / "ragas_test.md")
        agg = render(examples, results, output)

    assert agg.total == 1
    assert agg.successful == 1
    assert agg.mean_context_relevancy == pytest.approx(0.9)
    assert agg.mean_faithfulness == pytest.approx(0.88)


def test_render_handles_error_results():
    examples = [_make_example("e1"), _make_example("e2")]
    results = [
        _make_result("e1"),
        RagasResult(example_id="e2", error="skipped: empty contexts"),
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        output = str(Path(tmpdir) / "ragas_err.md")
        agg = render(examples, results, output)

    assert agg.total == 2
    assert agg.successful == 1


def test_render_creates_figures_directory():
    examples = [_make_example("e1")]
    results = [_make_result("e1")]

    with tempfile.TemporaryDirectory() as tmpdir:
        output = str(Path(tmpdir) / "reports" / "ragas_v1.md")
        render(examples, results, output)

        figures_dir = Path(tmpdir) / "reports" / "figures"
        assert figures_dir.exists()
        assert (figures_dir / "ragas_distribution.png").exists()
        assert (figures_dir / "ragas_per_company_bar.png").exists()
