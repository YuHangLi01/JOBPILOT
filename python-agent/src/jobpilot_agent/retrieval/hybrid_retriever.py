"""混合检索主入口：HybridRetriever。

这是 retrieval 层对外的唯一入口，所有下游调用（skills、graphs）都应通过它：

    from jobpilot_agent.retrieval import get_retriever, CollectionName, SearchOptions
    retriever = get_retriever(CollectionName.JD_KB)
    results = await retriever.search("Python 后端 3 年经验", CollectionName.JD_KB)

设计原则：
- 接口稳定（BaseRetriever）、实现可替换（构造函数注入 embedder/vector_store）
- 所有 CPU 密集型操作（embed、rerank）通过 asyncio.to_thread 不阻塞事件循环
- 两路检索（dense + sparse）并发执行，减少总延迟
- BM25 索引与 vector store 共享同一份 Document 数据，add_documents 同时写两处
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from jobpilot_agent.retrieval.base import BaseRetriever
from jobpilot_agent.retrieval.bm25 import BM25Index
from jobpilot_agent.retrieval.embedding import BaseEmbedder
from jobpilot_agent.retrieval.reranker import BGEReranker
from jobpilot_agent.retrieval.rrf_ranker import RRFRanker, WeightedRanker
from jobpilot_agent.retrieval.types import CollectionName, Document, RetrievalResult, SearchOptions
from jobpilot_agent.retrieval.vector_store import BaseVectorStore

logger = logging.getLogger(__name__)


class HybridRetriever(BaseRetriever):
    """混合检索器（Dense + Sparse + RRF + 可选 Rerank）。

    Args:
        embedder: Dense Embedding 实现（BaseEmbedder）。
        vector_store: 向量库实现（BaseVectorStore）。
        bm25_index: BM25 内存索引，与 collection 绑定。
        reranker: 可选的 Cross-Encoder 精排器。

    Example:
        >>> retriever = HybridRetriever(
        ...     embedder=get_embedder(),
        ...     vector_store=get_vector_store(),
        ...     bm25_index=BM25Index(CollectionName.JD_KB),
        ... )
        >>> results = await retriever.search(
        ...     "Python 3 年经验",
        ...     CollectionName.JD_KB,
        ...     SearchOptions(top_k=5),
        ... )
    """

    def __init__(
        self,
        embedder: BaseEmbedder,
        vector_store: BaseVectorStore,
        bm25_index: BM25Index,
        reranker: Optional[BGEReranker] = None,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store
        self._bm25 = bm25_index
        self._reranker = reranker
        self._collection = bm25_index.collection

        # 确保 vector store collection 已创建
        self._vector_store.create_collection(
            name=self._collection,
            dimension=self._embedder.dimension,
        )

    async def search(
        self,
        query: str,
        collection: CollectionName,
        options: SearchOptions = SearchOptions(),
    ) -> list[RetrievalResult]:
        """混合检索主入口。

        流程：
        query
          ├─(embed)→ dense 向量
          │           └─(vector_store.search)→ dense_results[dense_top_k]
          └─(tokenize + BM25.search)→ sparse_results[sparse_top_k]

        dense + sparse
          └─(RRFRanker or WeightedRanker)→ fused[rerank_top_k 或 top_k]

        fused
          ├─(enable_rerank=True)→ BGEReranker.rerank() → top_k
          └─(enable_rerank=False)→ fused[:top_k]

        Args:
            query: 检索词。
            collection: 目标集合（应与本 retriever 绑定的 collection 一致）。
            options: 检索选项。

        Returns:
            按最终 score 降序的 RetrievalResult，长度 <= options.top_k。
        """
        if collection != self._collection:
            raise ValueError(
                f"此 HybridRetriever 绑定 collection={self._collection.value!r}，"
                f"不支持 collection={collection.value!r}。请使用 get_retriever() 获取对应实例。"
            )

        # ── 并发执行两路检索 ──────────────────────────────────────────
        dense_task = self._dense_search(query, options)
        sparse_task = self._sparse_search(query, options)

        dense_results, sparse_results = await asyncio.gather(dense_task, sparse_task)

        logger.debug(
            "[HybridRetriever/%s] dense=%d, sparse=%d",
            collection.value,
            len(dense_results),
            len(sparse_results),
        )

        # ── 融合 ─────────────────────────────────────────────────────
        fuse_top_k = options.rerank_top_k if options.enable_rerank else options.top_k

        if options.dense_weight is not None and options.sparse_weight is not None:
            ranker: RRFRanker | WeightedRanker = WeightedRanker(
                dense_weight=options.dense_weight,
                sparse_weight=options.sparse_weight,
            )
        else:
            ranker = RRFRanker()

        fused = ranker.rank(dense_results, sparse_results, top_k=fuse_top_k)

        # ── 精排（可选） ─────────────────────────────────────────────
        if options.enable_rerank and self._reranker is not None and fused:
            final = await self._reranker.rerank(query, fused, top_k=options.top_k)
        else:
            if options.enable_rerank and self._reranker is None:
                logger.warning("enable_rerank=True 但 reranker 未配置，跳过精排")
            final = fused[: options.top_k]

        logger.debug(
            "[HybridRetriever/%s] 最终返回 %d 条，query=%r",
            collection.value,
            len(final),
            query[:40],
        )
        return final

    async def add_documents(
        self,
        collection: CollectionName,
        docs: list[Document],
    ) -> None:
        """批量写入文档（同时更新 vector store 和 BM25 索引）。

        步骤：
        1. 批量 embed 所有文档的 text
        2. upsert 到 vector store
        3. 将新文档合并到 BM25 内存索引（add_or_update，保留旧文档）

        Args:
            collection: 目标集合（必须与本 retriever 绑定的 collection 一致）。
            docs: 要写入的文档列表，相同 doc_id 会被覆盖（upsert 语义）。
        """
        if not docs:
            return

        if collection != self._collection:
            raise ValueError(
                f"collection mismatch: expected {self._collection.value!r}, "
                f"got {collection.value!r}"
            )

        # 批量 embed
        texts = [d.text for d in docs]
        embeddings = await self._embedder.embed_texts(texts)

        # 写入 vector store
        await self._vector_store.upsert(collection, docs, embeddings)

        # 更新 BM25 索引（增量，保留旧数据）
        self._bm25.add_or_update(docs)

        logger.info(
            "[HybridRetriever/%s] add_documents: %d 条写入完成",
            collection.value,
            len(docs),
        )

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    async def _dense_search(
        self, query: str, options: SearchOptions
    ) -> list[RetrievalResult]:
        """调用 embedder + vector_store 做 dense 检索。"""
        query_embedding = await self._embedder.embed_one(query)
        return await self._vector_store.search(
            collection=self._collection,
            query_embedding=query_embedding,
            top_k=options.dense_top_k,
            filters=options.filters,
        )

    async def _sparse_search(
        self, query: str, options: SearchOptions
    ) -> list[RetrievalResult]:
        """调用 BM25Index 做 sparse 检索。"""
        return self._bm25.search(
            query=query,
            top_k=options.sparse_top_k,
            filters=options.filters,
        )


# ---------------------------------------------------------------------------
# 单例工厂
# ---------------------------------------------------------------------------

_retriever_singletons: dict[CollectionName, HybridRetriever] = {}


def get_retriever(collection: CollectionName) -> HybridRetriever:
    """按 collection 返回缓存好的 HybridRetriever 实例（进程级单例）。

    首次调用时：
    1. 调用 get_embedder() 获取嵌入模型
    2. 调用 get_vector_store() 获取向量库（自动 Milvus→Chroma 降级）
    3. 创建对应 collection 的 BM25Index
    4. 按 settings.reranker_enabled_default 决定是否配置 BGEReranker

    Args:
        collection: 目标集合枚举。

    Returns:
        对应 collection 的 HybridRetriever 实例。

    Example:
        >>> retriever = get_retriever(CollectionName.INTERVIEW_KB)
        >>> results = await retriever.search("字节跳动 算法题", CollectionName.INTERVIEW_KB)
    """
    if collection in _retriever_singletons:
        return _retriever_singletons[collection]

    from jobpilot_agent.config import get_settings
    from jobpilot_agent.retrieval.embedding import get_embedder
    from jobpilot_agent.retrieval.vector_store import get_vector_store

    settings = get_settings()

    embedder = get_embedder()
    vector_store = get_vector_store()
    bm25_index = BM25Index(collection)

    reranker: Optional[BGEReranker] = None
    if getattr(settings, "reranker_enabled_default", False):
        reranker_model = getattr(settings, "reranker_model_name", "BAAI/bge-reranker-v2-m3")
        reranker = BGEReranker(model_name=reranker_model)

    retriever = HybridRetriever(
        embedder=embedder,
        vector_store=vector_store,
        bm25_index=bm25_index,
        reranker=reranker,
    )

    _retriever_singletons[collection] = retriever
    logger.info(
        "HybridRetriever[%s] 初始化完成（reranker=%s）",
        collection.value,
        reranker is not None,
    )
    return retriever


def reset_retriever_singletons() -> None:
    """重置所有 retriever 单例，主要供测试使用。"""
    _retriever_singletons.clear()
