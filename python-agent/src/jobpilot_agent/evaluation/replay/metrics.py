"""Replay 指标计算。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from jobpilot_agent.evaluation.replay.schema import (
    ReplayAggregateMetrics,
    ReplayResult,
    StageMetrics,
)
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

# BGE-M3 L2-norm cosine space: typical in-domain sim 0.35-0.65 (OpenAI space uses 0.75)
_SIMILARITY_THRESHOLD = 0.35


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """L2 归一化向量间的余弦相似度（= 点积）。"""
    return float(np.dot(a.flatten(), b.flatten()))


def compute_rank(
    real_emb: np.ndarray,
    cand_embs: list[np.ndarray],
    threshold: float = _SIMILARITY_THRESHOLD,
) -> tuple[int, bool, bool]:
    """计算真实追问在候选列表中的语义 rank。

    策略：对每个候选计算与真实追问的 cosine sim，按降序排，
    找第一个超过 threshold 的候选 → 返回其位置为 rank。
    全部未超 threshold → rank=99 (miss)。

    Returns:
        (rank, in_top_3, in_top_5)
    """
    sims = [cosine_similarity(real_emb, c) for c in cand_embs]
    sorted_indices = sorted(range(len(sims)), key=lambda i: -sims[i])

    for rank_pos, idx in enumerate(sorted_indices, start=1):
        if sims[idx] >= threshold:
            return rank_pos, rank_pos <= 3, rank_pos <= 5  # noqa: PLR2004

    return 99, False, False


def aggregate_metrics(results: list[ReplayResult]) -> ReplayAggregateMetrics:
    """从单次结果聚合为整体指标。"""
    successful = [r for r in results if r.error is None and r.bot_next_question]

    if not successful:
        return ReplayAggregateMetrics(
            total_pairs=len(results),
            successful_pairs=0,
            mean_similarity=0.0,
            median_similarity=0.0,
            rank_at_3=0.0,
            rank_at_5=0.0,
        )

    sims = [r.semantic_similarity for r in successful]
    mean_sim = float(np.mean(sims))
    median_sim = float(np.median(sims))
    rank_at_3 = sum(1 for r in successful if r.in_top_3) / len(successful)
    rank_at_5 = sum(1 for r in successful if r.in_top_5) / len(successful)

    # 分 stage
    stage_groups: dict[str, list[ReplayResult]] = defaultdict(list)
    for r in successful:
        stage_groups[r.stage].append(r)

    per_stage: dict[str, StageMetrics] = {}
    for stage, group in stage_groups.items():
        per_stage[stage] = StageMetrics(
            count=len(group),
            mean_similarity=float(np.mean([r.semantic_similarity for r in group])),
            rank_at_3=sum(1 for r in group if r.in_top_3) / len(group),
        )

    # per_company 需要 pairs 关联，在 aggregate_metrics_with_pairs 里填充
    per_company: dict[str, StageMetrics] = {}

    # 相似度分布
    similarity_distribution = {
        "<0.5": sum(1 for r in successful if r.semantic_similarity < 0.5),
        "0.5-0.7": sum(1 for r in successful if 0.5 <= r.semantic_similarity < 0.7),
        "0.7-0.85": sum(1 for r in successful if 0.7 <= r.semantic_similarity < 0.85),
        ">=0.85": sum(1 for r in successful if r.semantic_similarity >= 0.85),
    }

    log.info(
        "aggregate_metrics.done",
        total=len(results),
        successful=len(successful),
        mean_sim=round(mean_sim, 4),
        rank_at_3=round(rank_at_3, 4),
        rank_at_5=round(rank_at_5, 4),
    )
    return ReplayAggregateMetrics(
        total_pairs=len(results),
        successful_pairs=len(successful),
        mean_similarity=mean_sim,
        median_similarity=median_sim,
        rank_at_3=rank_at_3,
        rank_at_5=rank_at_5,
        per_stage=per_stage,
        per_company=per_company,
        similarity_distribution=similarity_distribution,
    )


def aggregate_metrics_with_pairs(
    results: list[ReplayResult],
    pairs: list[Any],  # list[ReplayPair]
) -> ReplayAggregateMetrics:
    """与 pairs 关联，补充 per_company 维度。"""
    pair_map = {p.pair_id: p for p in pairs}
    metrics = aggregate_metrics(results)

    successful = [r for r in results if r.error is None and r.bot_next_question]

    company_groups: dict[str, list[ReplayResult]] = defaultdict(list)
    for r in successful:
        pair = pair_map.get(r.pair_id)
        if pair:
            company_groups[pair.company].append(r)

    # 取前 10 公司（按数量）
    sorted_companies = sorted(company_groups.items(), key=lambda x: -len(x[1]))[:10]
    per_company: dict[str, StageMetrics] = {}
    for company, group in sorted_companies:
        per_company[company] = StageMetrics(
            count=len(group),
            mean_similarity=float(np.mean([r.semantic_similarity for r in group])),
            rank_at_3=sum(1 for r in group if r.in_top_3) / len(group),
        )

    metrics.per_company = per_company
    return metrics
