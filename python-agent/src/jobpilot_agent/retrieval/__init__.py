"""RAG 检索层公开 API。

下游模块（skills、graphs）只需从这里导入，无需关心具体实现：

    from jobpilot_agent.retrieval import (
        get_retriever,
        CollectionName,
        Document,
        RetrievalResult,
        SearchOptions,
    )

    retriever = get_retriever(CollectionName.JD_KB)
    results = await retriever.search(
        "Python 3年 后端 分布式",
        CollectionName.JD_KB,
        SearchOptions(top_k=5, enable_rerank=True),
    )
"""

from __future__ import annotations

from jobpilot_agent.retrieval.base import BaseRetriever
from jobpilot_agent.retrieval.bm25 import BM25Index
from jobpilot_agent.retrieval.embedding import BaseEmbedder, BGEM3Embedder, DoubaoEmbedder, get_embedder
from jobpilot_agent.retrieval.hybrid_retriever import HybridRetriever, get_retriever, reset_retriever_singletons
from jobpilot_agent.retrieval.reranker import BGEReranker
from jobpilot_agent.retrieval.rrf_ranker import RRFRanker, WeightedRanker
from jobpilot_agent.retrieval.tokenizer import tokenize_for_bm25
from jobpilot_agent.retrieval.types import CollectionName, Document, RetrievalResult, SearchOptions
from jobpilot_agent.retrieval.vector_store import (
    BaseVectorStore,
    ChromaVectorStore,
    MilvusVectorStore,
    get_vector_store,
    reset_vector_store_singleton,
)

async def search_interview_kb(
    query: str,
    top_k: int = 10,
    stage: str | None = None,
    company: str | None = None,
) -> list[RetrievalResult]:
    """面经知识库混合检索便利函数。

    `interview_rag` Skill 的专用入口，避免每次手动构造 SearchOptions。

    Args:
        query: 检索 query，如 "{company} {position} 面试"。
        top_k: 返回结果数量。
        stage: 面试阶段过滤，如 "tech_qa"、"project_deep_dive"；None 表示不过滤。
        company: 公司名过滤；None 表示不过滤。

    Returns:
        按 RRF 融合得分降序的 RetrievalResult 列表。
    """
    filters = {k: v for k, v in {"stage": stage, "company": company}.items() if v}
    retriever = get_retriever(CollectionName.INTERVIEW_KB)
    return await retriever.search(
        query,
        CollectionName.INTERVIEW_KB,
        SearchOptions(top_k=top_k, filters=filters or None),
    )


__all__ = [
    # 便利函数
    "search_interview_kb",
    # 核心入口
    "get_retriever",
    "reset_retriever_singletons",
    # 数据类型
    "CollectionName",
    "Document",
    "RetrievalResult",
    "SearchOptions",
    # 抽象基类
    "BaseRetriever",
    "BaseEmbedder",
    "BaseVectorStore",
    # 具体实现（供高级用户直接组合）
    "HybridRetriever",
    "BGEM3Embedder",
    "DoubaoEmbedder",
    "get_embedder",
    "BM25Index",
    "MilvusVectorStore",
    "ChromaVectorStore",
    "get_vector_store",
    "reset_vector_store_singleton",
    "RRFRanker",
    "WeightedRanker",
    "BGEReranker",
    "tokenize_for_bm25",
]
