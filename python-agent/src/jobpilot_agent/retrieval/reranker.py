"""Cross-Encoder 精排器。

BGEReranker 使用 BAAI/bge-reranker-v2-m3 对候选文档与 query 做交叉编码打分，
相比双塔模型（Bi-Encoder）精度更高，但延迟也更高（约 200ms/10条）。

建议仅在 SearchOptions.enable_rerank=True 时调用，且 candidates 数量不超过 20 条。
"""

from __future__ import annotations

import asyncio
import logging

from jobpilot_agent.retrieval.types import RetrievalResult

logger = logging.getLogger(__name__)

_BATCH_SIZE_RERANK = 16


class BGEReranker:
    """BAAI/bge-reranker-v2-m3 Cross-Encoder 精排器。

    首次调用 rerank 时触发模型加载（约 500MB 下载）。
    建议配置 HF_ENDPOINT=https://hf-mirror.com 加速国内下载。

    Args:
        model_name: HuggingFace 模型 ID，默认 "BAAI/bge-reranker-v2-m3"。

    Example:
        >>> reranker = BGEReranker()
        >>> results = asyncio.run(reranker.rerank("Python 后端", candidates, top_k=3))
        >>> # results[0].rerank_score 为 Cross-Encoder 打分
        >>> # results[0].score 已替换为 rerank_score
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self._model_name = model_name
        self._model: object | None = None  # 惰性加载

    def _load_model(self) -> object:
        """惰性加载 CrossEncoder，线程安全。"""
        if self._model is None:
            logger.info(
                "正在加载 Reranker 模型 %s，首次加载可能需要下载（约 500MB）…",
                self._model_name,
            )
            from sentence_transformers import CrossEncoder  # type: ignore[import]

            self._model = CrossEncoder(self._model_name)
            logger.info("Reranker 模型加载完毕：%s", self._model_name)
        return self._model

    def _score_sync(self, query: str, texts: list[str]) -> list[float]:
        """同步批量打分，在 to_thread 中调用。"""
        model = self._load_model()
        pairs = [[query, t] for t in texts]
        scores: list[float] = model.predict(  # type: ignore[union-attr]
            pairs,
            batch_size=_BATCH_SIZE_RERANK,
            show_progress_bar=False,
        ).tolist()
        return scores

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int = 3,
    ) -> list[RetrievalResult]:
        """对候选列表做 Cross-Encoder 精排。

        流程：
        1. 从 candidates 提取 text
        2. 与 query 组成 (query, text) pair 送入 CrossEncoder.predict()
        3. 按 cross-encoder 分数降序排列，截取 top_k
        4. 填充 rerank_score，并将 score 字段替换为 rerank_score

        Args:
            query: 检索词。
            candidates: 待精排的候选列表（通常是 RRF 融合后的 top-10~20 条）。
            top_k: 精排后返回数量。

        Returns:
            按 rerank_score 降序排列的 RetrievalResult 列表，
            每条的 score 字段已替换为 rerank_score。
        """
        if not candidates:
            return []

        texts = [r.text for r in candidates]
        scores = await asyncio.to_thread(self._score_sync, query, texts)

        # 组装结果
        scored_candidates = list(zip(scores, candidates))
        scored_candidates.sort(key=lambda x: (-x[0], x[1].doc_id))

        results: list[RetrievalResult] = []
        for rerank_score, cand in scored_candidates[:top_k]:
            rs = float(rerank_score)
            results.append(
                RetrievalResult(
                    doc_id=cand.doc_id,
                    text=cand.text,
                    metadata=cand.metadata,
                    score=rs,  # 用 rerank_score 覆盖 score
                    dense_score=cand.dense_score,
                    sparse_score=cand.sparse_score,
                    rerank_score=rs,
                    rank_in_dense=cand.rank_in_dense,
                    rank_in_sparse=cand.rank_in_sparse,
                )
            )

        logger.debug(
            "Reranker：candidates=%d → top_%d，最高分=%.4f",
            len(candidates),
            len(results),
            results[0].rerank_score if results else 0.0,
        )
        return results
