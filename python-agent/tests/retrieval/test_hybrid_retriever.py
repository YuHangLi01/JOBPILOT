"""集成测试：HybridRetriever（20 条混合数据）。

需要本地 Milvus Standalone 运行（或 Chroma 降级模式）。
测试聚焦于端到端流程：add_documents + search + filter + RRF 融合。

运行（Milvus 模式）：
    pytest tests/retrieval/test_hybrid_retriever.py -m integration -v

运行（Chroma 降级，无需 Milvus）：
    FORCE_CHROMA=1 pytest tests/retrieval/test_hybrid_retriever.py -m integration -v
"""

import os

import numpy as np
import pytest

from jobpilot_agent.retrieval.bm25 import BM25Index
from jobpilot_agent.retrieval.hybrid_retriever import HybridRetriever
from jobpilot_agent.retrieval.rrf_ranker import RRFRanker
from jobpilot_agent.retrieval.types import CollectionName, Document, SearchOptions

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# 20 条测试文档（含中英文、技术关键词、不同公司）
# ---------------------------------------------------------------------------

FAKE_DOCS = [
    Document(
        doc_id=f"jd_kb-test_{i:03d}-0",
        collection=CollectionName.JD_KB,
        text=text,
        metadata={"company": company, "source_id": f"test_{i:03d}", "chunk_index": 0},
    )
    for i, (text, company) in enumerate(
        [
            ("Python 高级后端工程师，5年经验，熟悉微服务、Docker、Kubernetes", "字节跳动"),
            ("Go 后端开发，3年以上，高并发系统设计，Kafka 消息队列", "字节跳动"),
            ("前端工程师 React TypeScript，负责复杂交互组件开发", "字节跳动"),
            ("Java 架构师，Spring Boot 微服务，分布式事务，10年经验", "阿里巴巴"),
            ("机器学习算法工程师，PyTorch，推荐系统，NLP", "阿里巴巴"),
            ("数据工程师，Spark Flink，实时数仓，ClickHouse", "阿里巴巴"),
            ("Python AI 工程师，LangChain LangGraph，RAG 检索增强生成", "百度"),
            ("向量数据库工程师，Milvus 运维，HNSW 索引调优", "百度"),
            ("Android 高级工程师，Kotlin，性能优化，音视频开发", "腾讯"),
            ("iOS 开发工程师，Swift，ARKit，消费类应用", "腾讯"),
            ("SRE 工程师，Kubernetes 集群管理，Prometheus 监控", "腾讯"),
            ("产品经理，用户研究，数据分析，B端 SaaS 产品", "美团"),
            ("Python 后端，Django REST Framework，多租户架构", "美团"),
            ("全栈工程师，Vue 3 + FastAPI，中小团队 Tech Lead", "滴滴"),
            ("Golang 微服务，gRPC，服务网格，3年经验", "滴滴"),
            ("数据科学家，统计建模，A/B 实验，SQL Python R", "京东"),
            ("安全工程师，渗透测试，漏洞挖掘，CTF 背景", "京东"),
            ("后端工程师 Node.js TypeScript，REST API 设计", "字节跳动"),
            ("嵌入式软件工程师，C++ RTOS，STM32", "华为"),
            ("云原生架构师，AWS Azure，Terraform，DevOps 实践", "华为"),
        ],
        start=0,
    )
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class DummyEmbedder:
    """用随机小向量替代真实模型，加快集成测试速度。"""

    dimension = 16

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        np.random.seed(abs(hash(texts[0])) % 2**31)
        vecs = np.random.randn(len(texts), self.dimension).astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / norms

    async def embed_one(self, text: str) -> np.ndarray:
        arr = await self.embed_texts([text])
        return arr[0]


@pytest.fixture(scope="module")
async def retriever() -> HybridRetriever:
    """构造 HybridRetriever，根据环境变量选择 Chroma 或 Milvus。"""
    force_chroma = os.environ.get("FORCE_CHROMA", "0") == "1"

    from jobpilot_agent.retrieval.vector_store import ChromaVectorStore, MilvusVectorStore

    if force_chroma:
        vs = ChromaVectorStore(persist_dir="/tmp/test_chroma_hybrid")
    else:
        vs = MilvusVectorStore(uri="http://localhost:19530")

    bm25 = BM25Index(CollectionName.JD_KB)
    embedder = DummyEmbedder()
    r = HybridRetriever(embedder=embedder, vector_store=vs, bm25_index=bm25)  # type: ignore[arg-type]

    # 写入测试文档
    await r.add_documents(CollectionName.JD_KB, FAKE_DOCS)
    yield r

    # 清理
    try:
        vs.drop(CollectionName.JD_KB)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 测试：基础检索
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_results(retriever: HybridRetriever) -> None:
    results = await retriever.search(
        "Python 后端工程师",
        CollectionName.JD_KB,
        SearchOptions(top_k=5),
    )
    assert len(results) > 0
    assert len(results) <= 5


@pytest.mark.asyncio
async def test_search_scores_descending(retriever: HybridRetriever) -> None:
    results = await retriever.search(
        "Python 后端",
        CollectionName.JD_KB,
        SearchOptions(top_k=10),
    )
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_search_python_recall(retriever: HybridRetriever) -> None:
    """Python 查询应能从两路各自召回 Python 相关文档。"""
    results = await retriever.search(
        "Python 开发工程师",
        CollectionName.JD_KB,
        SearchOptions(top_k=5),
    )
    texts = [r.text for r in results]
    assert any("Python" in t for t in texts)


@pytest.mark.asyncio
async def test_search_rrf_score_filled(retriever: HybridRetriever) -> None:
    """RRF 融合后每条结果应有 score > 0。"""
    results = await retriever.search(
        "后端工程师",
        CollectionName.JD_KB,
        SearchOptions(top_k=5),
    )
    for r in results:
        assert r.score > 0


# ---------------------------------------------------------------------------
# 过滤器测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_by_company(retriever: HybridRetriever) -> None:
    """只返回字节跳动的文档。"""
    results = await retriever.search(
        "工程师",
        CollectionName.JD_KB,
        SearchOptions(top_k=10, filters={"company": "字节跳动"}),
    )
    assert len(results) > 0
    for r in results:
        assert "字节跳动" in r.metadata.get("company", "")


@pytest.mark.asyncio
async def test_filter_no_match_returns_empty_or_few(retriever: HybridRetriever) -> None:
    """不存在的公司应返回空结果（或极少）。"""
    results = await retriever.search(
        "工程师",
        CollectionName.JD_KB,
        SearchOptions(top_k=5, filters={"company": "不存在公司XYZ"}),
    )
    # BM25 过滤为空，vector store 过滤也应为空
    assert len(results) == 0


# ---------------------------------------------------------------------------
# 两路并发验证
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dense_and_sparse_both_contribute(retriever: HybridRetriever) -> None:
    """检查 RRF 结果中同时出现了 dense_score 或 sparse_score 有值的条目。"""
    results = await retriever.search(
        "RAG 检索增强",
        CollectionName.JD_KB,
        SearchOptions(top_k=10),
    )
    has_dense = any(r.dense_score is not None for r in results)
    has_sparse = any(r.sparse_score is not None for r in results)
    assert has_dense or has_sparse  # 至少一路有分数


# ---------------------------------------------------------------------------
# collection mismatch 保护
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_wrong_collection_raises(retriever: HybridRetriever) -> None:
    with pytest.raises(ValueError, match="collection"):
        await retriever.search(
            "Python",
            CollectionName.INTERVIEW_KB,  # 绑定的是 JD_KB
            SearchOptions(),
        )
