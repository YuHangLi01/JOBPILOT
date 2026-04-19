"""端到端延迟指标计算。

基于 RunRecord.total_latency_ms 和 per_node_latency_ms 统计各分位数。
"""

from __future__ import annotations

from pydantic import BaseModel

from jobpilot_agent.evaluation.runners.scenario_a_runner import RunRecord

_NODE_NAMES = [
    "parse_jd",
    "classify_jd",
    "dispatch_skills",
    "invoke_skills_parallel",
    "merge_outputs",
    "final_synthesis",
]


class NodeLatency(BaseModel):
    """单个节点的延迟统计。

    Attributes:
        p50_ms: 中位数延迟（ms）。
        p95_ms: 95 分位延迟（ms）。
        mean_ms: 平均延迟（ms）。
        sample_count: 参与统计的样本数。
    """

    p50_ms: float
    p95_ms: float
    mean_ms: float
    sample_count: int


class LatencyMetrics(BaseModel):
    """端到端延迟统计。

    Attributes:
        p50_ms: 端到端中位数延迟。
        p90_ms: 端到端 P90 延迟。
        p95_ms: 端到端 P95 延迟。
        p99_ms: 端到端 P99 延迟。
        mean_ms: 端到端平均延迟。
        max_ms: 端到端最大延迟。
        min_ms: 端到端最小延迟。
        evaluated_count: 参与统计的有效样本数。
        per_node: 各节点延迟统计。
    """

    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    max_ms: float
    min_ms: float
    evaluated_count: int
    per_node: dict[str, NodeLatency]


def compute_latency_metrics(records: list[RunRecord]) -> LatencyMetrics:
    """使用 numpy.percentile 计算延迟分布指标。

    只使用 success=True 且 total_latency_ms > 0 的记录。

    Args:
        records: RunRecord 列表。

    Returns:
        LatencyMetrics 实例。
    """
    import numpy as np  # type: ignore[import]

    valid = [r for r in records if r.success and r.total_latency_ms > 0]
    if not valid:
        raise ValueError("没有有效的延迟记录（success=True 且 latency > 0）")

    latencies = np.array([r.total_latency_ms for r in valid], dtype=float)

    # ── 端到端分位数 ─────────────────────────────────────────────────
    p50, p90, p95, p99 = float(np.percentile(latencies, 50)), float(np.percentile(latencies, 90)), float(np.percentile(latencies, 95)), float(np.percentile(latencies, 99))
    mean_ms = float(np.mean(latencies))
    max_ms = float(np.max(latencies))
    min_ms = float(np.min(latencies))

    # ── 各节点延迟 ───────────────────────────────────────────────────
    per_node: dict[str, NodeLatency] = {}
    for node in _NODE_NAMES:
        node_latencies = [
            r.per_node_latency_ms[node]
            for r in valid
            if node in r.per_node_latency_ms
        ]
        if node_latencies:
            arr = np.array(node_latencies, dtype=float)
            per_node[node] = NodeLatency(
                p50_ms=float(np.percentile(arr, 50)),
                p95_ms=float(np.percentile(arr, 95)),
                mean_ms=float(np.mean(arr)),
                sample_count=len(node_latencies),
            )

    return LatencyMetrics(
        p50_ms=p50,
        p90_ms=p90,
        p95_ms=p95,
        p99_ms=p99,
        mean_ms=mean_ms,
        max_ms=max_ms,
        min_ms=min_ms,
        evaluated_count=len(valid),
        per_node=per_node,
    )
