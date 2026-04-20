"""RRF（Reciprocal Rank Fusion）及加权融合排序。

经典 RRF 公式：
    score(d) = Σ_i  1 / (k + rank_i(d))

其中：
- k：平滑参数，默认 60（学术标准值）
- rank_i(d)：文档 d 在第 i 路结果中的排名，从 1 开始
- 若 d 不在第 i 路结果中，rank_i 视为 len(results_i) + 1（有限大，而非 inf）

设计说明：
- RRFRanker 是「排名融合」，不是「分数融合」——这是 RRF 的核心价值，
  解决了两路分数（cosine similarity vs BM25 score）不同尺度的问题
- WeightedRanker 在两路分数均归一化到 [0,1] 后做加权求和，
  适用于已知两路权重配比的场景
"""

from __future__ import annotations

import logging

from jobpilot_agent.retrieval.types import RetrievalResult

logger = logging.getLogger(__name__)


class RRFRanker:
    """Reciprocal Rank Fusion 融合排序。

    Args:
        k: 平滑参数。k=60 是 Cormack et al. 2009 的推荐值。
            - k 越小：第 1 名的权重越高（结果越"激进"）
            - k 越大：各名次权重越均匀（结果越"保守"）

    Example:
        >>> ranker = RRFRanker(k=60)
        >>> fused = ranker.rank(dense_results, sparse_results, top_k=5)
        >>> # fused[0].score 为 RRF 融合分，dense_score/sparse_score 保留原始分
    """

    def __init__(self, k: int = 60) -> None:
        if k <= 0:
            raise ValueError(f"k 必须为正整数，got {k}")
        self.k = k

    def rank(
        self,
        dense_results: list[RetrievalResult],
        sparse_results: list[RetrievalResult],
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """对两路结果做 RRF 融合。

        算法步骤：
        1. 为每路结果建立 doc_id → rank 映射（rank 从 1 开始）
        2. 计算 union(dense_doc_ids, sparse_doc_ids) 中每个 doc_id 的 RRF 分：
               rrf_score = 1/(k + rank_dense) + 1/(k + rank_sparse)
           若 doc_id 不在某一路，该路 rank = max_rank + 1
        3. 按 rrf_score 降序排列，截取 top_k
        4. 将原始 dense_score / sparse_score / rank_in_* 附加到结果

        Args:
            dense_results: 向量检索结果，已按 dense_score 降序。
            sparse_results: BM25 检索结果，已按 sparse_score 降序。
            top_k: 最终返回结果数量。

        Returns:
            按 RRF score 降序排列的 RetrievalResult 列表，score 为 RRF 融合分。
        """
        if not dense_results and not sparse_results:
            return []

        # ── 建立 rank 映射 ──────────────────────────────────────────
        # rank 从 1 开始；absent rank = len(该路) + 1（有限大值）
        dense_rank: dict[str, int] = {r.doc_id: i for i, r in enumerate(dense_results, 1)}
        sparse_rank: dict[str, int] = {r.doc_id: i for i, r in enumerate(sparse_results, 1)}

        absent_dense = len(dense_results) + 1
        absent_sparse = len(sparse_results) + 1

        # ── 收集所有 doc_id ─────────────────────────────────────────
        all_doc_ids = set(dense_rank) | set(sparse_rank)

        # ── 用于快速查 RetrievalResult 的字典 ──────────────────────
        dense_by_id = {r.doc_id: r for r in dense_results}
        sparse_by_id = {r.doc_id: r for r in sparse_results}

        # ── 计算 RRF 分 ─────────────────────────────────────────────
        scored: list[tuple[float, str]] = []
        for doc_id in all_doc_ids:
            rd = dense_rank.get(doc_id, absent_dense)
            rs = sparse_rank.get(doc_id, absent_sparse)
            rrf_score = 1.0 / (self.k + rd) + 1.0 / (self.k + rs)
            scored.append((rrf_score, doc_id))

        # 降序排列（分数相同时按 doc_id 字典序，保证确定性）
        scored.sort(key=lambda x: (-x[0], x[1]))

        # ── 组装结果 ─────────────────────────────────────────────────
        results: list[RetrievalResult] = []
        for rrf_score, doc_id in scored[:top_k]:
            # 优先取 dense 结果里的文本（分数更高时一般更相关）
            base = dense_by_id.get(doc_id) or sparse_by_id[doc_id]

            results.append(
                RetrievalResult(
                    doc_id=doc_id,
                    text=base.text,
                    metadata=base.metadata,
                    score=rrf_score,
                    dense_score=dense_by_id[doc_id].dense_score if doc_id in dense_by_id else None,
                    sparse_score=sparse_by_id[doc_id].sparse_score if doc_id in sparse_by_id else None,
                    rank_in_dense=dense_rank.get(doc_id),
                    rank_in_sparse=sparse_rank.get(doc_id),
                )
            )

        logger.debug(
            "RRF(k=%d): dense=%d, sparse=%d → fused top-%d",
            self.k,
            len(dense_results),
            len(sparse_results),
            len(results),
        )
        return results


class WeightedRanker:
    """加权线性融合排序。

    先将两路分数各自归一化到 [0, 1]，再按权重加权求和：
        weighted_score = w_dense * norm_dense + w_sparse * norm_sparse

    适用场景：当你清楚地知道某个场景更依赖关键词匹配（加大 sparse_weight）
    或更依赖语义相似度（加大 dense_weight）时使用。

    Args:
        dense_weight: dense 路的权重，与 sparse_weight 之和不必等于 1。
        sparse_weight: sparse 路的权重。

    Example:
        >>> ranker = WeightedRanker(dense_weight=0.7, sparse_weight=0.3)
        >>> fused = ranker.rank(dense_results, sparse_results, top_k=5)
    """

    def __init__(self, dense_weight: float, sparse_weight: float) -> None:
        if dense_weight < 0 or sparse_weight < 0:
            raise ValueError("权重不能为负数")
        if dense_weight == 0 and sparse_weight == 0:
            raise ValueError("dense_weight 与 sparse_weight 不能同时为 0")
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

    def rank(
        self,
        dense_results: list[RetrievalResult],
        sparse_results: list[RetrievalResult],
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        """加权融合两路结果。

        步骤：
        1. 各路 score 做 min-max 归一化到 [0, 1]
        2. 对 union 集合计算加权分（不在某路的 doc 该路归一化分为 0）
        3. 降序截取 top_k

        Args:
            dense_results: 向量检索结果。
            sparse_results: BM25 检索结果。
            top_k: 最终返回结果数量。

        Returns:
            按加权 score 降序排列的 RetrievalResult 列表。
        """
        if not dense_results and not sparse_results:
            return []

        # ── min-max 归一化 ────────────────────────────────────────────
        dense_normalized = _normalize_scores(dense_results, "dense")
        sparse_normalized = _normalize_scores(sparse_results, "sparse")

        # ── 合并 ──────────────────────────────────────────────────────
        dense_by_id = {r.doc_id: r for r in dense_results}
        sparse_by_id = {r.doc_id: r for r in sparse_results}

        all_doc_ids = set(dense_normalized) | set(sparse_normalized)

        scored: list[tuple[float, str]] = []
        for doc_id in all_doc_ids:
            nd = dense_normalized.get(doc_id, 0.0)
            ns = sparse_normalized.get(doc_id, 0.0)
            w_score = self.dense_weight * nd + self.sparse_weight * ns
            scored.append((w_score, doc_id))

        scored.sort(key=lambda x: (-x[0], x[1]))

        results: list[RetrievalResult] = []
        for w_score, doc_id in scored[:top_k]:
            base = dense_by_id.get(doc_id) or sparse_by_id[doc_id]
            results.append(
                RetrievalResult(
                    doc_id=doc_id,
                    text=base.text,
                    metadata=base.metadata,
                    score=w_score,
                    dense_score=dense_by_id[doc_id].dense_score if doc_id in dense_by_id else None,
                    sparse_score=sparse_by_id[doc_id].sparse_score if doc_id in sparse_by_id else None,
                    rank_in_dense=next(
                        (i for i, r in enumerate(dense_results, 1) if r.doc_id == doc_id), None
                    ),
                    rank_in_sparse=next(
                        (i for i, r in enumerate(sparse_results, 1) if r.doc_id == doc_id), None
                    ),
                )
            )

        logger.debug(
            "WeightedRanker(d=%.2f, s=%.2f): dense=%d, sparse=%d → fused top-%d",
            self.dense_weight,
            self.sparse_weight,
            len(dense_results),
            len(sparse_results),
            len(results),
        )
        return results


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _normalize_scores(
    results: list[RetrievalResult],
    score_field: str,
) -> dict[str, float]:
    """对检索结果的指定分数字段做 min-max 归一化，返回 doc_id → 归一化分数 的字典。

    Args:
        results: 检索结果列表。
        score_field: 分数字段名，"dense" 或 "sparse"。

    Returns:
        doc_id → [0,1] 归一化分数。
    """
    if not results:
        return {}

    attr = "dense_score" if score_field == "dense" else "sparse_score"
    raw_scores = [getattr(r, attr) or r.score for r in results]

    min_s = min(raw_scores)
    max_s = max(raw_scores)
    diff = max_s - min_s

    normalized: dict[str, float] = {}
    for r, s in zip(results, raw_scores):
        if diff == 0:
            normalized[r.doc_id] = 1.0
        else:
            normalized[r.doc_id] = (s - min_s) / diff

    return normalized
