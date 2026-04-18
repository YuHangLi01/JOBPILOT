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

__all__ = [
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
