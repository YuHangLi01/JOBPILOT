"""向量库封装：Milvus（主）+ Chroma（降级）。

设计说明：
- BaseVectorStore 定义接口，MilvusVectorStore / ChromaVectorStore 各自实现
- get_vector_store() 在启动时探测 Milvus 连通性，不可用则自动切换 Chroma
- 所有 Collection 共享相同 Schema 模板（HNSW，动态字段）
- upsert 语义：相同 doc_id 覆盖（Milvus delete + insert）
- search 返回 RetrievalResult，dense_score 已填充
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

import numpy as np

from jobpilot_agent.retrieval.types import CollectionName, Document, RetrievalResult

logger = logging.getLogger(__name__)

# Milvus HNSW 默认索引参数
_HNSW_INDEX_PARAMS = {
    "index_type": "HNSW",
    "metric_type": "COSINE",
    "params": {"M": 16, "efConstruction": 200},
}
_HNSW_SEARCH_PARAMS = {"ef": 64}

# 通用 Schema 字段定义
_COMMON_FIELDS = [
    {"name": "doc_id", "dtype": "VARCHAR", "is_primary": True, "max_length": 128},
    {"name": "text", "dtype": "VARCHAR", "max_length": 8192},
    {"name": "embedding", "dtype": "FLOAT_VECTOR"},  # dim 在运行时填充
    {"name": "source_id", "dtype": "VARCHAR", "max_length": 64, "default_value": ""},
    {"name": "chunk_index", "dtype": "INT64", "default_value": 0},
    {"name": "company", "dtype": "VARCHAR", "max_length": 64, "default_value": ""},
    {"name": "position", "dtype": "VARCHAR", "max_length": 128, "default_value": ""},
]


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------


class BaseVectorStore(ABC):
    """向量库抽象基类，屏蔽底层实现差异。"""

    @abstractmethod
    def create_collection(
        self,
        name: CollectionName,
        dimension: int,
        metric_type: str = "COSINE",
    ) -> None:
        """幂等创建集合（已存在则跳过）。"""
        ...

    @abstractmethod
    async def upsert(
        self,
        collection: CollectionName,
        docs: list[Document],
        embeddings: np.ndarray,
    ) -> None:
        """批量 upsert 文档（相同 doc_id 覆盖）。"""
        ...

    @abstractmethod
    async def search(
        self,
        collection: CollectionName,
        query_embedding: np.ndarray,
        top_k: int = 20,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[RetrievalResult]:
        """稠密向量检索，返回 top_k 条结果。"""
        ...

    @abstractmethod
    def count(self, collection: CollectionName) -> int:
        """返回集合中的文档数量。"""
        ...

    @abstractmethod
    def drop(self, collection: CollectionName) -> None:
        """删除集合（谨慎使用）。"""
        ...

    @abstractmethod
    def list_collections(self) -> list[str]:
        """列出所有已创建的集合名称。"""
        ...


# ---------------------------------------------------------------------------
# Milvus 实现
# ---------------------------------------------------------------------------


class MilvusVectorStore(BaseVectorStore):
    """基于 pymilvus 2.4 的向量库封装。

    Args:
        uri: Milvus 服务地址，如 "http://localhost:19530"。
        db_name: 数据库名称，默认 "default"。

    Example:
        >>> store = MilvusVectorStore(uri="http://localhost:19530")
        >>> store.create_collection(CollectionName.JD_KB, dimension=1024)
    """

    def __init__(self, uri: str, db_name: str = "default") -> None:
        from pymilvus import MilvusClient  # type: ignore[import]

        self._client: Any = MilvusClient(uri=uri, db_name=db_name)
        self._uri = uri
        logger.info("MilvusVectorStore 连接到 %s / %s", uri, db_name)

    def create_collection(
        self,
        name: CollectionName,
        dimension: int,
        metric_type: str = "COSINE",
    ) -> None:
        """幂等创建 collection，已存在则跳过。

        Args:
            name: 集合枚举。
            dimension: 向量维度（与 embedder.dimension 一致）。
            metric_type: 距离度量，默认 COSINE。
        """
        col_name = name.value
        if self._client.has_collection(col_name):
            logger.debug("Collection %s 已存在，跳过创建", col_name)
            return

        from pymilvus import DataType, MilvusClient  # type: ignore[import]

        schema = MilvusClient.create_schema(
            auto_id=False,
            enable_dynamic_field=True,
        )
        schema.add_field("doc_id", DataType.VARCHAR, is_primary=True, max_length=128)
        schema.add_field("text", DataType.VARCHAR, max_length=8192)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dimension)
        schema.add_field("source_id", DataType.VARCHAR, max_length=64)
        schema.add_field("chunk_index", DataType.INT64)
        schema.add_field("company", DataType.VARCHAR, max_length=64)
        schema.add_field("position", DataType.VARCHAR, max_length=128)

        index_params = self._client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="HNSW",
            metric_type=metric_type,
            params={"M": 16, "efConstruction": 200},
        )

        self._client.create_collection(
            collection_name=col_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info("Collection %s 创建完成，dim=%d", col_name, dimension)

    async def upsert(
        self,
        collection: CollectionName,
        docs: list[Document],
        embeddings: np.ndarray,
    ) -> None:
        """批量 upsert。先删除已有同 doc_id 记录，再插入。

        Args:
            collection: 目标集合。
            docs: 文档列表，len(docs) == embeddings.shape[0]。
            embeddings: shape=(N, dim) 的 float32 归一化向量。
        """
        if not docs:
            return

        col_name = collection.value

        def _do_upsert() -> None:
            doc_ids = [d.doc_id for d in docs]
            # 先删除旧记录（幂等）
            filter_expr = " || ".join(f'doc_id == "{did}"' for did in doc_ids)
            try:
                self._client.delete(collection_name=col_name, filter=filter_expr)
            except Exception:
                pass  # 首次插入时不存在，忽略

            rows = []
            for doc, emb in zip(docs, embeddings):
                row: dict[str, Any] = {
                    "doc_id": doc.doc_id,
                    "text": doc.text,
                    "embedding": emb.tolist(),
                    "source_id": doc.metadata.get("source_id", ""),
                    "chunk_index": doc.metadata.get("chunk_index", 0),
                    "company": doc.metadata.get("company", ""),
                    "position": doc.metadata.get("position", ""),
                }
                # 其他 metadata 字段写入动态字段
                for k, v in doc.metadata.items():
                    if k not in row:
                        row[k] = v
                rows.append(row)

            self._client.insert(collection_name=col_name, data=rows)
            logger.debug("[Milvus/%s] upsert %d 条", col_name, len(rows))

        await asyncio.to_thread(_do_upsert)

    async def search(
        self,
        collection: CollectionName,
        query_embedding: np.ndarray,
        top_k: int = 20,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[RetrievalResult]:
        """稠密向量检索。

        Args:
            collection: 目标集合。
            query_embedding: shape=(dim,) 的查询向量（已归一化）。
            top_k: 返回结果数量上限。
            filters: 标量过滤，如 {"company": "字节跳动"}。
                转换为 Milvus 布尔表达式（精确匹配）。

        Returns:
            按 dense_score 降序的 RetrievalResult 列表。
        """
        col_name = collection.value

        filter_expr = _build_milvus_filter(filters)

        def _do_search() -> list[dict[str, Any]]:
            results = self._client.search(
                collection_name=col_name,
                data=[query_embedding.tolist()],
                limit=top_k,
                search_params={"metric_type": "COSINE", "params": {"ef": 64}},
                filter=filter_expr if filter_expr else None,
                output_fields=["doc_id", "text", "source_id", "chunk_index", "company", "position"],
            )
            return results[0] if results else []

        raw = await asyncio.to_thread(_do_search)

        results: list[RetrievalResult] = []
        for rank, hit in enumerate(raw, start=1):
            entity = hit.get("entity", hit)
            score = float(hit.get("distance", 0.0))
            results.append(
                RetrievalResult(
                    doc_id=entity.get("doc_id", ""),
                    text=entity.get("text", ""),
                    metadata={
                        k: entity.get(k)
                        for k in ("source_id", "chunk_index", "company", "position")
                        if entity.get(k) is not None
                    },
                    score=score,
                    dense_score=score,
                    rank_in_dense=rank,
                )
            )
        return results

    def count(self, collection: CollectionName) -> int:
        stats = self._client.get_collection_stats(collection.value)
        return int(stats.get("row_count", 0))

    def drop(self, collection: CollectionName) -> None:
        self._client.drop_collection(collection.value)
        logger.warning("Collection %s 已删除", collection.value)

    def list_collections(self) -> list[str]:
        return self._client.list_collections()


# ---------------------------------------------------------------------------
# Chroma 降级实现
# ---------------------------------------------------------------------------


class ChromaVectorStore(BaseVectorStore):
    """基于 chromadb 的本地向量库（Milvus 不可用时的降级方案）。

    Args:
        persist_dir: 持久化目录，默认 "./data/chroma"。

    Note:
        Chroma 无需单独启动服务，数据写到本地磁盘，适合开发/单测。
        与 MilvusVectorStore 接口完全相同，HybridRetriever 无感知切换。
    """

    def __init__(self, persist_dir: str = "./data/chroma") -> None:
        import chromadb  # type: ignore[import]

        self._client: Any = chromadb.PersistentClient(path=persist_dir)
        self._collections: dict[str, Any] = {}
        logger.info("ChromaVectorStore 初始化，持久化目录：%s", persist_dir)

    def _get_or_create(self, name: CollectionName) -> Any:
        col_name = name.value
        if col_name not in self._collections:
            self._collections[col_name] = self._client.get_or_create_collection(
                name=col_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[col_name]

    def create_collection(
        self,
        name: CollectionName,
        dimension: int,
        metric_type: str = "COSINE",
    ) -> None:
        self._get_or_create(name)
        logger.debug("Chroma collection %s 已就绪", name.value)

    async def upsert(
        self,
        collection: CollectionName,
        docs: list[Document],
        embeddings: np.ndarray,
    ) -> None:
        if not docs:
            return

        col = self._get_or_create(collection)

        def _do_upsert() -> None:
            col.upsert(
                ids=[d.doc_id for d in docs],
                documents=[d.text for d in docs],
                embeddings=embeddings.tolist(),
                metadatas=[d.metadata for d in docs],
            )

        await asyncio.to_thread(_do_upsert)
        logger.debug("[Chroma/%s] upsert %d 条", collection.value, len(docs))

    async def search(
        self,
        collection: CollectionName,
        query_embedding: np.ndarray,
        top_k: int = 20,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[RetrievalResult]:
        col = self._get_or_create(collection)

        where = _build_chroma_filter(filters) if filters else None

        def _do_search() -> Any:
            kwargs: dict[str, Any] = {
                "query_embeddings": [query_embedding.tolist()],
                "n_results": top_k,
                "include": ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where
            return col.query(**kwargs)

        raw = await asyncio.to_thread(_do_search)

        results: list[RetrievalResult] = []
        ids = raw.get("ids", [[]])[0]
        docs_texts = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        for rank, (doc_id, text, meta, dist) in enumerate(
            zip(ids, docs_texts, metas, distances), start=1
        ):
            # Chroma cosine distance ∈ [0, 2]，转换为 similarity ∈ [-1, 1]
            score = float(1.0 - dist)
            results.append(
                RetrievalResult(
                    doc_id=doc_id,
                    text=text or "",
                    metadata=meta or {},
                    score=score,
                    dense_score=score,
                    rank_in_dense=rank,
                )
            )
        return results

    def count(self, collection: CollectionName) -> int:
        return self._get_or_create(collection).count()

    def drop(self, collection: CollectionName) -> None:
        self._client.delete_collection(collection.value)
        self._collections.pop(collection.value, None)
        logger.warning("Chroma collection %s 已删除", collection.value)

    def list_collections(self) -> list[str]:
        return [c.name for c in self._client.list_collections()]


# ---------------------------------------------------------------------------
# 过滤表达式构建
# ---------------------------------------------------------------------------


def _build_milvus_filter(filters: Optional[dict[str, Any]]) -> str:
    """将 filters 字典转换为 Milvus 布尔表达式字符串。

    Args:
        filters: 如 {"company": "字节跳动", "stage": "tech_qa"}。

    Returns:
        Milvus filter 字符串，如 'company == "字节跳动" && stage == "tech_qa"'。
        空 filters 返回 ""。
    """
    if not filters:
        return ""
    parts = []
    for k, v in filters.items():
        if isinstance(v, str):
            escaped = v.replace('"', '\\"')
            parts.append(f'{k} == "{escaped}"')
        elif isinstance(v, (int, float)):
            parts.append(f"{k} == {v}")
    return " && ".join(parts)


def _build_chroma_filter(filters: dict[str, Any]) -> dict[str, Any]:
    """将 filters 字典转换为 Chroma where 子句。

    Args:
        filters: 如 {"company": "字节跳动"}。

    Returns:
        Chroma where 格式，如 {"company": {"$eq": "字节跳动"}}。
    """
    if len(filters) == 1:
        k, v = next(iter(filters.items()))
        return {k: {"$eq": v}}
    # 多条件用 $and
    return {"$and": [{k: {"$eq": v}} for k, v in filters.items()]}


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------

_vector_store_singleton: Optional[BaseVectorStore] = None


def get_vector_store(force_chroma: bool = False) -> BaseVectorStore:
    """根据 Milvus 连通性返回合适的向量库实例（进程级单例）。

    逻辑：
    1. 若 force_chroma=True，直接返回 Chroma（用于测试）
    2. 否则尝试连通 Milvus；成功返回 MilvusVectorStore
    3. 连通失败且 retrieval_fallback_to_chroma=True，返回 ChromaVectorStore
    4. 连通失败且不允许降级，抛出异常

    Args:
        force_chroma: 强制使用 Chroma，跳过 Milvus 探活。

    Returns:
        BaseVectorStore 实例。
    """
    global _vector_store_singleton

    if _vector_store_singleton is not None:
        return _vector_store_singleton

    from jobpilot_agent.config import get_settings

    settings = get_settings()

    if force_chroma:
        _vector_store_singleton = ChromaVectorStore(
            persist_dir=getattr(settings, "chroma_persist_dir", "./data/chroma")
        )
        return _vector_store_singleton

    # 尝试连通 Milvus
    milvus_uri = settings.milvus_uri
    try:
        from pymilvus import MilvusClient  # type: ignore[import]

        test_client: Any = MilvusClient(uri=milvus_uri)
        test_client.list_collections()  # 简单 ping
        db_name = getattr(settings, "milvus_db_name", "default")
        _vector_store_singleton = MilvusVectorStore(uri=milvus_uri, db_name=db_name)
        logger.info("Milvus 连通，使用 MilvusVectorStore（%s）", milvus_uri)
    except Exception as exc:
        fallback = getattr(settings, "retrieval_fallback_to_chroma", True)
        if fallback:
            logger.warning(
                "Milvus 不可用（%s），自动降级到 Chroma：%s",
                milvus_uri,
                exc,
            )
            chroma_dir = getattr(settings, "chroma_persist_dir", "./data/chroma")
            _vector_store_singleton = ChromaVectorStore(persist_dir=chroma_dir)
        else:
            raise RuntimeError(
                f"Milvus 连接失败（{milvus_uri}），且未启用降级。错误：{exc}"
            ) from exc

    return _vector_store_singleton


def reset_vector_store_singleton() -> None:
    """重置单例，主要供测试使用。"""
    global _vector_store_singleton
    _vector_store_singleton = None
