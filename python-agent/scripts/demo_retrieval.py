"""演示检索层：正常路径（Milvus）与自动降级路径（Chroma）。

用法：
    cd python-agent

    # 路径 1：尝试连接 Milvus，不可用时自动切 Chroma
    uv run python scripts/demo_retrieval.py

    # 路径 2：强制使用 Chroma（无需 Milvus）
    uv run python scripts/demo_retrieval.py --chroma

环境要求：
    LLM_API_KEY=any-value-for-schema-export（脚本中已内置占位符）

输出示例（3 条假数据 hybrid search 结果，含 dense_rank/sparse_rank/rrf_score）：
    ────────────────────────────────────────
    Top 1  doc_id=jd_kb-test_006-0
           rrf_score=0.0328  dense_rank=1  sparse_rank=2
           text: Python AI 工程师，LangChain LangGraph，RAG 检索增强生成
    ────────────────────────────────────────
    ...
"""

import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Optional

# 让脚本在不安装包的情况下也能运行（src layout）
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# 注入占位环境变量，避免 pydantic-settings 报错
os.environ.setdefault("LLM_API_KEY", "demo-placeholder")
os.environ.setdefault("POSTGRES_URL", "postgresql://demo/demo")
os.environ.setdefault("APP_ENV", "dev")

import argparse
import logging

import numpy as np

logging.basicConfig(
    level=logging.WARNING,  # 关闭框架 INFO 日志，只看演示输出
    format="%(levelname)s %(name)s: %(message)s",
)

from jobpilot_agent.retrieval.bm25 import BM25Index
from jobpilot_agent.retrieval.hybrid_retriever import HybridRetriever
from jobpilot_agent.retrieval.rrf_ranker import RRFRanker
from jobpilot_agent.retrieval.types import CollectionName, Document, RetrievalResult, SearchOptions
from jobpilot_agent.retrieval.vector_store import ChromaVectorStore, reset_vector_store_singleton

# ---------------------------------------------------------------------------
# 假嵌入模型（避免下载 2GB 真实模型）
# ---------------------------------------------------------------------------


class DeterministicEmbedder:
    """基于文本 hash 生成确定性小向量，用于演示，不依赖真实模型。"""

    dimension = 32

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        vecs = []
        for text in texts:
            seed = abs(hash(text)) % (2**31)
            rng = np.random.default_rng(seed)
            v = rng.standard_normal(self.dimension).astype(np.float32)
            v /= np.linalg.norm(v)
            vecs.append(v)
        return np.stack(vecs)

    async def embed_one(self, text: str) -> np.ndarray:
        arr = await self.embed_texts([text])
        return arr[0]


# ---------------------------------------------------------------------------
# 测试文档（20 条）
# ---------------------------------------------------------------------------

DEMO_DOCS = [
    Document(
        doc_id=f"jd_kb-test_{i:03d}-0",
        collection=CollectionName.JD_KB,
        text=text,
        metadata={"company": company, "source_id": f"test_{i:03d}"},
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
# 演示函数
# ---------------------------------------------------------------------------


def print_separator(title: str = "") -> None:
    line = "─" * 60
    if title:
        print(f"\n{line}")
        print(f"  {title}")
        print(line)
    else:
        print(line)


def print_result(rank: int, r: RetrievalResult) -> None:
    print(
        f"  Top {rank}  doc_id={r.doc_id}\n"
        f"        rrf_score={r.score:.6f}  "
        f"dense_rank={r.rank_in_dense}  "
        f"sparse_rank={r.rank_in_sparse}\n"
        f"        text: {r.text[:70]}"
    )
    print()


async def run_demo(use_chroma: bool) -> None:
    store_type = "Chroma（降级）" if use_chroma else "Milvus（正常路径）"
    print_separator(f"JobPilot RAG 检索层演示 — {store_type}")

    # ── 向量库 ───────────────────────────────────────────────
    if use_chroma:
        import tempfile

        chroma_dir = tempfile.mkdtemp(prefix="demo_chroma_")
        print(f"  Chroma 持久化目录：{chroma_dir}")
        vector_store = ChromaVectorStore(persist_dir=chroma_dir)
    else:
        reset_vector_store_singleton()
        os.environ["RETRIEVAL_FALLBACK_TO_CHROMA"] = "true"
        from jobpilot_agent.retrieval.vector_store import get_vector_store

        vector_store = get_vector_store()

    # ── 构造 Retriever ────────────────────────────────────────
    embedder = DeterministicEmbedder()
    bm25_index = BM25Index(CollectionName.JD_KB)
    retriever = HybridRetriever(
        embedder=embedder,  # type: ignore[arg-type]
        vector_store=vector_store,
        bm25_index=bm25_index,
    )

    # ── 写入文档 ──────────────────────────────────────────────
    print(f"\n  写入 {len(DEMO_DOCS)} 条测试文档…")
    t0 = time.perf_counter()
    await retriever.add_documents(CollectionName.JD_KB, DEMO_DOCS)
    print(f"  写入完成，耗时 {(time.perf_counter() - t0) * 1000:.0f}ms")

    # ── 场景 1：Python AI 工程师 ──────────────────────────────
    query1 = "Python AI 工程师 RAG 检索"
    print_separator(f'查询："{query1}"')
    t0 = time.perf_counter()
    results1 = await retriever.search(
        query1, CollectionName.JD_KB, SearchOptions(top_k=3)
    )
    latency1 = (time.perf_counter() - t0) * 1000
    for i, r in enumerate(results1, 1):
        print_result(i, r)
    print(f"  延迟：{latency1:.1f}ms")

    # ── 场景 2：过滤字节跳动 ──────────────────────────────────
    query2 = "后端工程师"
    print_separator(f'查询："{query2}"  filter: company=字节跳动')
    t0 = time.perf_counter()
    results2 = await retriever.search(
        query2,
        CollectionName.JD_KB,
        SearchOptions(top_k=3, filters={"company": "字节跳动"}),
    )
    latency2 = (time.perf_counter() - t0) * 1000
    for i, r in enumerate(results2, 1):
        print_result(i, r)
    print(f"  延迟：{latency2:.1f}ms")

    # ── 场景 3：WeightedRanker ────────────────────────────────
    query3 = "Kubernetes 运维"
    print_separator(f'查询："{query3}"  WeightedRanker(dense=0.3, sparse=0.7)')
    t0 = time.perf_counter()
    results3 = await retriever.search(
        query3,
        CollectionName.JD_KB,
        SearchOptions(top_k=3, dense_weight=0.3, sparse_weight=0.7),
    )
    latency3 = (time.perf_counter() - t0) * 1000
    for i, r in enumerate(results3, 1):
        print_result(i, r)
    print(f"  延迟：{latency3:.1f}ms")

    # ── 总结 ─────────────────────────────────────────────────
    print_separator("验收总结")
    print(f"  向量库：{vector_store.__class__.__name__}")
    print(f"  文档数：{len(DEMO_DOCS)}")
    print(f"  场景 1 延迟：{latency1:.1f}ms  {'[OK]' if latency1 < 500 else '[SLOW > 500ms]'}")
    print(f"  场景 2 延迟：{latency2:.1f}ms  {'[OK]' if latency2 < 500 else '[SLOW > 500ms]'}")
    print(f"  场景 3 延迟：{latency3:.1f}ms  {'[OK]' if latency3 < 500 else '[SLOW > 500ms]'}")
    print()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="JobPilot RAG 检索层演示")
    parser.add_argument("--chroma", action="store_true", help="强制使用 Chroma（无需 Milvus）")
    args = parser.parse_args()

    asyncio.run(run_demo(use_chroma=args.chroma))


if __name__ == "__main__":
    main()
