"""Dense Embedding 封装。

设计原则：
- BaseEmbedder 定义接口，下游代码不感知具体实现
- BGEM3Embedder：本地 sentence-transformers，惰性加载（首次 embed 时才加载模型）
- DoubaoEmbedder：火山方舟远程 API，OpenAI 兼容格式
- get_embedder()：根据 config 返回单例，用 lru_cache 保证全局只加载一次
- 输出必须 L2 归一化（Milvus COSINE 度量对已归一化向量等价于内积，搜索更快）
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from abc import ABC, abstractmethod
from collections import OrderedDict
from functools import lru_cache
from threading import Lock
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

_BATCH_SIZE_DENSE = 32
_BATCH_SIZE_DOUBAO = 16  # 远程 API 并发更保守


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------


class BaseEmbedder(ABC):
    """Embedding 模型抽象基类。

    所有 embedder 实现必须：
    1. 返回 L2 归一化（unit norm）的 np.ndarray，shape=(N, dim)
    2. embed_texts 为 async，CPU 密集型操作用 asyncio.to_thread 包裹
    """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度。"""
        ...

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        """将文本列表批量转换为 L2 归一化向量。

        Args:
            texts: 待嵌入文本列表，不应为空。

        Returns:
            np.ndarray，shape=(len(texts), self.dimension)，dtype=float32，
            每行已做 L2 归一化（||v||=1）。
        """
        ...

    async def embed_one(self, text: str) -> np.ndarray:
        """对单条文本做嵌入，shape=(dim,)。

        Args:
            text: 待嵌入文本。

        Returns:
            shape=(self.dimension,) 的归一化向量。
        """
        arr = await self.embed_texts([text])
        return arr[0]


# ---------------------------------------------------------------------------
# 本地 BGE-M3
# ---------------------------------------------------------------------------


class BGEM3Embedder(BaseEmbedder):
    """本地 sentence-transformers BAAI/bge-m3 嵌入模型。

    首次调用 embed_texts 时触发模型加载（约 2GB 下载，耗时因网速而异）。
    建议配置 HF_ENDPOINT=https://hf-mirror.com 加速国内下载。

    Args:
        model_name: HuggingFace 模型 ID，默认 "BAAI/bge-m3"。
        device: 推理设备，"auto" 时自动选 cuda/mps/cpu。

    Example:
        >>> embedder = BGEM3Embedder()
        >>> vecs = asyncio.run(embedder.embed_texts(["Python 后端", "机器学习"]))
        >>> vecs.shape  # (2, 1024)
        (2, 1024)
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "auto",
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model: object | None = None  # 惰性加载

    @property
    def dimension(self) -> int:
        return 1024

    def _load_model(self) -> object:
        """惰性加载 SentenceTransformer，线程安全（GIL 保护单次 import）。"""
        if self._model is None:
            logger.info(
                "正在加载本地 Embedding 模型 %s，首次加载可能需要下载（约 2GB）…",
                self._model_name,
            )
            from sentence_transformers import SentenceTransformer  # type: ignore[import]

            self._model = SentenceTransformer(
                self._model_name,
                device=None if self._device == "auto" else self._device,
            )
            logger.info("Embedding 模型加载完毕：%s", self._model_name)
        return self._model

    def _encode_sync(self, texts: list[str]) -> np.ndarray:
        """同步批量编码，在 to_thread 中运行以避免阻塞事件循环。"""
        model = self._load_model()
        # sentence-transformers SentenceTransformer
        embeddings: np.ndarray = model.encode(  # type: ignore[union-attr]
            texts,
            batch_size=_BATCH_SIZE_DENSE,
            normalize_embeddings=True,  # L2 归一化
            show_progress_bar=False,
        )
        return embeddings.astype(np.float32)

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        """异步批量嵌入。CPU 密集型，用 asyncio.to_thread 移入线程池。

        Args:
            texts: 待嵌入文本列表。

        Returns:
            shape=(len(texts), 1024) 的 float32 归一化向量矩阵。
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        return await asyncio.to_thread(self._encode_sync, texts)


# ---------------------------------------------------------------------------
# 远程火山方舟 Embedding
# ---------------------------------------------------------------------------


class DoubaoEmbedder(BaseEmbedder):
    """火山方舟远程 Embedding API（OpenAI 兼容格式）。

    适合没有本地 GPU 或演示场景，依赖网络，受 RPM 限制。

    Args:
        api_key: 火山方舟 API Key。
        model: 嵌入模型名称，如 "doubao-embedding"。
        base_url: API 基础地址。
        dimension: 向量维度，与所选模型一致。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "doubao-embedding",
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        dimension: int = 1024,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._dim = dimension
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    @property
    def dimension(self) -> int:
        return self._dim

    async def _get_client(self) -> "httpx.AsyncClient":
        """返回复用的 AsyncClient；首次调用时懒初始化（线程/协程安全）。"""
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    import httpx  # type: ignore[import]

                    self._client = httpx.AsyncClient(
                        base_url=self._base_url,
                        timeout=30.0,
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        limits=httpx.Limits(
                            max_connections=20,
                            max_keepalive_connections=10,
                        ),
                    )
        return self._client

    async def aclose(self) -> None:
        """关闭底层 httpx 连接池。由 FastAPI lifespan shutdown 调用。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        """调用远程 API 批量嵌入。

        Args:
            texts: 待嵌入文本列表。

        Returns:
            shape=(len(texts), self.dimension) 的 float32 归一化向量矩阵。
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        client = await self._get_client()
        all_vectors: list[list[float]] = []

        # 分批请求，避免单次请求过大；客户端复用连接池，显著降低 TLS 握手开销
        for i in range(0, len(texts), _BATCH_SIZE_DOUBAO):
            batch = texts[i : i + _BATCH_SIZE_DOUBAO]
            resp = await client.post(
                "/embeddings",
                json={"model": self._model, "input": batch},
            )
            resp.raise_for_status()
            data = resp.json()
            for item in data["data"]:
                all_vectors.append(item["embedding"])

        arr = np.array(all_vectors, dtype=np.float32)
        return _l2_normalize(arr)


# ---------------------------------------------------------------------------
# LRU 缓存包装器
# ---------------------------------------------------------------------------


class CachedEmbedder(BaseEmbedder):
    """给任何 BaseEmbedder 套上内存 LRU 缓存层。

    设计要点：
    - key = sha256(text)[:16]，避免长文本占用大量内存
    - 只缓存已 L2 归一化的向量（和底层 embedder 的契约一致）
    - 线程安全：缓存本身用 threading.Lock 守护；内部 embedder 的 async 调用
      在 gather 外做（miss 列表先收集再一次 batch embed）
    - 并发安全：同一文本的并发 miss 会产生重复计算，但结果正确；
      后写覆盖前写不会破坏数据（相同 key → 相同 embedding）

    Args:
        inner: 被包装的 embedder。
        max_size: 最大缓存条目数（默认 10000）。
    """

    def __init__(self, inner: BaseEmbedder, max_size: int = 10000) -> None:
        self._inner = inner
        self._max_size = max_size
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    @property
    def dimension(self) -> int:
        return self._inner.dimension

    @property
    def inner(self) -> BaseEmbedder:
        return self._inner

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _get(self, key: str) -> np.ndarray | None:
        with self._lock:
            vec = self._cache.get(key)
            if vec is not None:
                # move_to_end 保证 LRU 语义
                self._cache.move_to_end(key)
            return vec

    def _put(self, key: str, vec: np.ndarray) -> None:
        with self._lock:
            self._cache[key] = vec
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)  # 弹出最久未使用

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        results: list[np.ndarray | None] = [None] * len(texts)
        miss_indices: list[int] = []
        miss_texts: list[str] = []

        for i, text in enumerate(texts):
            key = self._cache_key(text)
            cached = self._get(key)
            if cached is not None:
                results[i] = cached
                self._hits += 1
            else:
                miss_indices.append(i)
                miss_texts.append(text)
                self._misses += 1

        if miss_texts:
            new_embeddings = await self._inner.embed_texts(miss_texts)
            for idx, text, vec in zip(miss_indices, miss_texts, new_embeddings):
                results[idx] = vec
                self._put(self._cache_key(text), vec)

        return np.array(results, dtype=np.float32)

    async def aclose(self) -> None:
        """转发给内部 embedder（如果它是远程客户端）。"""
        close = getattr(self._inner, "aclose", None)
        if close is not None and callable(close):
            await close()

    def cache_stats(self) -> dict[str, float | int]:
        total = self._hits + self._misses
        with self._lock:
            size = len(self._cache)
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": size,
            "max_size": self._max_size,
            "hit_rate": (self._hits / total) if total else 0.0,
        }


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """对每行向量做 L2 归一化。

    Args:
        vectors: shape=(N, D)。

    Returns:
        归一化后的矩阵，||row||=1。
    """
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)  # 防止零向量除以 0
    return vectors / norms


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_embedder() -> BaseEmbedder:
    """根据配置返回 Embedder 单例。

    读取 config.embedding_provider：
    - "local"  → BGEM3Embedder（本地模型）
    - "doubao" → DoubaoEmbedder（远程 API）

    Returns:
        BaseEmbedder 实例，全程只创建一次。

    Raises:
        ValueError: 当 EMBEDDING_PROVIDER 配置值无效时。
    """
    from jobpilot_agent.config import get_settings

    settings = get_settings()
    provider = getattr(settings, "embedding_provider", "local")

    inner: BaseEmbedder
    if provider == "local":
        logger.info("使用本地 Embedding 模型：%s", settings.embedding_model_name)
        inner = BGEM3Embedder(model_name=settings.embedding_model_name)
    elif provider == "doubao":
        logger.info("使用远程 Doubao Embedding API")
        inner = DoubaoEmbedder(
            api_key=settings.llm_api_key,
            base_url=settings.llm_api_base_url,
        )
    else:
        raise ValueError(
            f"未知的 EMBEDDING_PROVIDER: {provider!r}，有效值为 'local' 或 'doubao'"
        )

    if getattr(settings, "embedding_cache_enabled", True):
        max_size = getattr(settings, "embedding_cache_size", 10000)
        logger.info("启用 Embedding LRU 缓存，max_size=%d", max_size)
        return CachedEmbedder(inner, max_size=max_size)
    return inner
