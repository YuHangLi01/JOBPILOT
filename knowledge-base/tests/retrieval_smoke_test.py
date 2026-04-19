"""召回质量 smoke 测试 —— 20 个 case，≥85% 通过为合格。

运行方式：
    uv run pytest tests/retrieval_smoke_test.py -m integration -s

产物：
    data/retrieval_smoke_report.md
"""

from __future__ import annotations

import asyncio
import statistics
import time
from pathlib import Path
from typing import Any, Literal, Optional

import pytest
from pydantic import BaseModel, Field

from jobpilot_agent.retrieval import (
    CollectionName,
    RetrievalResult,
    SearchOptions,
    get_retriever,
)

pytestmark = pytest.mark.integration

_REPORT_PATH = Path("data/retrieval_smoke_report.md")


CollectionLiteral = Literal["jd_kb", "interview_kb", "user_kb"]


class SmokeCase(BaseModel):
    collection: CollectionLiteral
    query: str
    filters: Optional[dict[str, Any]] = None
    expected_metadata_contains: dict[str, Any] = Field(default_factory=dict)
    min_rank: int = 5


SMOKE_TEST_CASES: list[SmokeCase] = [
    # ─────────────────────────── jd_kb ────────────────────────────
    SmokeCase(
        collection="jd_kb",
        query="高级前端工程师 React TypeScript",
        expected_metadata_contains={"sub_type": "frontend"},
        min_rank=5,
    ),
    SmokeCase(
        collection="jd_kb",
        query="产品经理",
        filters={"job_type": "product"},
        expected_metadata_contains={"job_type": "product"},
        min_rank=1,
    ),
    SmokeCase(
        collection="jd_kb",
        query="算法工程师 机器学习",
        filters={"job_type": "tech"},
        expected_metadata_contains={"job_type": "tech"},
        min_rank=3,
    ),
    SmokeCase(
        collection="jd_kb",
        query="初级 应届 实习",
        expected_metadata_contains={"level": "junior"},
        min_rank=5,
    ),
    SmokeCase(
        collection="jd_kb",
        query="Golang 后端 分布式",
        expected_metadata_contains={"job_type": "tech"},
        min_rank=5,
    ),
    SmokeCase(
        collection="jd_kb",
        query="设计师 UI",
        filters={"job_type": "design"},
        expected_metadata_contains={"job_type": "design"},
        min_rank=3,
    ),
    SmokeCase(
        collection="jd_kb",
        query="运营 用户增长",
        filters={"job_type": "ops"},
        expected_metadata_contains={"job_type": "ops"},
        min_rank=3,
    ),
    # ───────────────────────── interview_kb ────────────────────────
    SmokeCase(
        collection="interview_kb",
        query="React hooks 原理",
        filters={"stage": "tech_qa"},
        expected_metadata_contains={"stage": "tech_qa"},
        min_rank=5,
    ),
    SmokeCase(
        collection="interview_kb",
        query="项目难点 挑战",
        filters={"stage": "project_deep_dive"},
        expected_metadata_contains={"stage": "project_deep_dive"},
        min_rank=5,
    ),
    SmokeCase(
        collection="interview_kb",
        query="自我介绍",
        filters={"stage": "intro"},
        expected_metadata_contains={"stage": "intro"},
        min_rank=3,
    ),
    SmokeCase(
        collection="interview_kb",
        query="梯度消失 解决方法",
        expected_metadata_contains={"stage": "tech_qa"},
        min_rank=5,
    ),
    SmokeCase(
        collection="interview_kb",
        query="BatchNorm LayerNorm 区别",
        expected_metadata_contains={"stage": "tech_qa"},
        min_rank=5,
    ),
    SmokeCase(
        collection="interview_kb",
        query="BERT 文本分类 NER",
        expected_metadata_contains={"role": "candidate"},
        min_rank=5,
    ),
    SmokeCase(
        collection="interview_kb",
        query="Transformer Multi-Head Attention 作用",
        filters={"stage": "tech_qa"},
        expected_metadata_contains={"stage": "tech_qa"},
        min_rank=5,
    ),
    # ─────────────────────────── user_kb ───────────────────────────
    SmokeCase(
        collection="user_kb",
        query="JobPilot 项目",
        filters={"user_id": "u_default"},
        expected_metadata_contains={"user_id": "u_default"},
        min_rank=2,
    ),
    SmokeCase(
        collection="user_kb",
        query="南京大学 研究生",
        filters={"user_id": "u_sample_fresh_grad"},
        expected_metadata_contains={"section": "education"},
        min_rank=3,
    ),
    SmokeCase(
        collection="user_kb",
        query="AntV BizCharts 升级",
        filters={"user_id": "u_sample_senior_fe"},
        expected_metadata_contains={"section": "work_experience"},
        min_rank=3,
    ),
    SmokeCase(
        collection="user_kb",
        query="AI 产品经理 北极星指标",
        filters={"user_id": "u_sample_product"},
        expected_metadata_contains={"user_id": "u_sample_product"},
        min_rank=3,
    ),
    SmokeCase(
        collection="user_kb",
        query="Python 后端 Milvus",
        filters={"user_id": "u_default", "section": "skills"},
        expected_metadata_contains={"section": "skills"},
        min_rank=2,
    ),
    SmokeCase(
        collection="user_kb",
        query="ACM 竞赛",
        filters={"user_id": "u_sample_fresh_grad"},
        expected_metadata_contains={"user_id": "u_sample_fresh_grad"},
        min_rank=3,
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class CaseOutcome(BaseModel):
    case: SmokeCase
    passed: bool
    hit_rank: Optional[int]
    latency_ms: float
    top_k_preview: list[dict[str, Any]]
    dense_avg: float
    sparse_avg: float


def _contains(meta: dict[str, Any], expected: dict[str, Any]) -> bool:
    for k, v in expected.items():
        if k not in meta:
            return False
        if str(v).lower() not in str(meta[k]).lower():
            return False
    return True


async def _run_case(case: SmokeCase) -> CaseOutcome:
    col = CollectionName(case.collection)
    retriever = get_retriever(col)

    opts = SearchOptions(top_k=5, filters=case.filters)
    t0 = time.perf_counter()
    results: list[RetrievalResult] = await retriever.search(case.query, col, opts)
    latency_ms = (time.perf_counter() - t0) * 1000

    hit_rank: Optional[int] = None
    for rank, r in enumerate(results, start=1):
        if _contains(r.metadata, case.expected_metadata_contains):
            hit_rank = rank
            break

    dense_scores = [r.dense_score for r in results if r.dense_score is not None]
    sparse_scores = [r.sparse_score for r in results if r.sparse_score is not None]

    return CaseOutcome(
        case=case,
        passed=hit_rank is not None and hit_rank <= case.min_rank,
        hit_rank=hit_rank,
        latency_ms=latency_ms,
        top_k_preview=[
            {"doc_id": r.doc_id, "score": r.score, "metadata": r.metadata, "text": r.text[:120]}
            for r in results[:5]
        ],
        dense_avg=statistics.mean(dense_scores) if dense_scores else 0.0,
        sparse_avg=statistics.mean(sparse_scores) if sparse_scores else 0.0,
    )


async def _run_all() -> list[CaseOutcome]:
    return [await _run_case(case) for case in SMOKE_TEST_CASES]


def _render_report(outcomes: list[CaseOutcome]) -> str:
    total = len(outcomes)
    passed = sum(1 for o in outcomes if o.passed)
    rate = passed / total if total else 0.0

    lines = [
        "# Retrieval Smoke Report",
        "",
        f"- Total: {total}",
        f"- Passed: {passed}",
        f"- Pass rate: **{rate * 100:.1f}%** (target ≥ 85%)",
        f"- Avg latency: {statistics.mean([o.latency_ms for o in outcomes]):.1f} ms",
        "",
        "## Per-collection stats",
        "",
        "| Collection | Cases | Pass | Avg latency | Avg dense | Avg sparse |",
        "|-----------|-------|------|-------------|-----------|------------|",
    ]

    for col in ("jd_kb", "interview_kb", "user_kb"):
        sub = [o for o in outcomes if o.case.collection == col]
        if not sub:
            continue
        sub_pass = sum(1 for o in sub if o.passed)
        lines.append(
            f"| `{col}` | {len(sub)} | {sub_pass} | "
            f"{statistics.mean([o.latency_ms for o in sub]):.1f} ms | "
            f"{statistics.mean([o.dense_avg for o in sub]):.3f} | "
            f"{statistics.mean([o.sparse_avg for o in sub]):.3f} |"
        )

    lines += ["", "## Failures"]
    failures = [o for o in outcomes if not o.passed]
    if not failures:
        lines.append("None.")
    else:
        for i, o in enumerate(failures, start=1):
            lines += [
                "",
                f"### {i}. query={o.case.query!r} (collection={o.case.collection})",
                "",
                f"- filters: `{o.case.filters}`",
                f"- expected: `{o.case.expected_metadata_contains}` (min_rank={o.case.min_rank})",
                f"- actual hit_rank: {o.hit_rank}",
                "- top-5:",
            ]
            for r in o.top_k_preview:
                lines.append(
                    f"  - `{r['doc_id']}` score={r['score']:.3f} meta={r['metadata']} text={r['text']!r}"
                )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Pytest 入口
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieval_smoke() -> None:
    outcomes = await _run_all()
    report = _render_report(outcomes)
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(report, encoding="utf-8")

    total = len(outcomes)
    passed = sum(1 for o in outcomes if o.passed)
    rate = passed / total

    avg_latency = statistics.mean([o.latency_ms for o in outcomes])
    assert rate >= 0.85, (
        f"pass rate {rate:.2%} < 85%，详见 {_REPORT_PATH}"
    )
    assert avg_latency < 300, f"平均延迟 {avg_latency:.1f} ms 超过 300ms 门槛"


if __name__ == "__main__":
    outcomes = asyncio.run(_run_all())
    report = _render_report(outcomes)
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
