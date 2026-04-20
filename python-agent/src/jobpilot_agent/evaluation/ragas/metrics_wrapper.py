"""RAGAS 指标包装器 — NaN 处理 + 聚合计算。"""

from __future__ import annotations

import math

from jobpilot_agent.evaluation.ragas.schema import (
    RagasAggregate,
    RagasCompanyMetric,
    RagasExample,
    RagasResult,
)


def safe_float(v: object) -> float:
    """将 RAGAS 偶发的 NaN / None 值归零。"""
    if v is None:
        return 0.0
    f = float(v)  # type: ignore[arg-type]
    if math.isnan(f) or math.isinf(f):
        return 0.0
    return f


def _group_metric(
    results: list[RagasResult],
    example_map: dict[str, RagasExample],
    key_fn,
) -> dict[str, RagasCompanyMetric]:
    """按 key_fn 分组聚合成 RagasCompanyMetric。"""
    import numpy as np

    groups: dict[str, list[RagasResult]] = {}
    for r in results:
        if r.error:
            continue
        ex = example_map.get(r.example_id)
        if ex is None:
            continue
        k = key_fn(ex)  # key_fn receives RagasExample
        groups.setdefault(k, []).append(r)

    out: dict[str, RagasCompanyMetric] = {}
    for k, rs in groups.items():
        out[k] = RagasCompanyMetric(
            count=len(rs),
            mean_context_relevancy=float(np.mean([safe_float(r.context_relevancy) for r in rs])),
            mean_context_recall=float(np.mean([safe_float(r.context_recall) for r in rs])),
            mean_faithfulness=float(np.mean([safe_float(r.faithfulness) for r in rs])),
            mean_answer_relevancy=float(np.mean([safe_float(r.answer_relevancy) for r in rs])),
        )
    return out


def aggregate_results(
    results: list[RagasResult],
    examples: list[RagasExample],
) -> RagasAggregate:
    """将 list[RagasResult] 聚合为 RagasAggregate。

    - 只统计 error is None 的成功样本
    - NaN 值通过 safe_float 归零后再平均
    """
    import numpy as np

    successful = [r for r in results if r.error is None]
    example_map = {e.example_id: e for e in examples}

    def _mean(vals: list[float]) -> float:
        return float(np.mean(vals)) if vals else 0.0

    cr = _mean([safe_float(r.context_relevancy) for r in successful])
    cre = _mean([safe_float(r.context_recall) for r in successful])
    fai = _mean([safe_float(r.faithfulness) for r in successful])
    ar = _mean([safe_float(r.answer_relevancy) for r in successful])

    by_company = _group_metric(results, example_map, lambda e: e.company)
    by_job_type = _group_metric(results, example_map, lambda e: e.job_type or "unknown")

    return RagasAggregate(
        total=len(results),
        successful=len(successful),
        mean_context_relevancy=cr,
        mean_context_recall=cre,
        mean_faithfulness=fai,
        mean_answer_relevancy=ar,
        by_company=by_company,
        by_job_type=by_job_type,
    )
