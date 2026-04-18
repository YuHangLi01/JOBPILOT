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
import logging
from abc import ABC, abstractmethod
from functools import lru_cache

import numpy as np

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

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_texts(self, texts: list[str]) -> np.ndarray:
        """调用远程 API 批量嵌入。

        Args:
            texts: 待嵌入文本列表。

        Returns:
            shape=(len(texts), self.dimension) 的 float32 归一化向量矩阵。
        """
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)

        import httpx  # type: ignore[import]

        all_vectors: list[list[float]] = []

        # 分批请求，避免单次请求过大
        for i in range(0, len(texts), _BATCH_SIZE_DOUBAO):
            batch = texts[i : i + _BATCH_SIZE_DOUBAO]
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": self._model, "input": batch},
                )
                resp.raise_for_status()
                data = resp.json()
                for item in data["data"]:
                    all_vectors.append(item["embedding"])

        arr = np.array(all_vectors, dtype=np.float32)
        return _l2_normalize(arr)


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

    if provider == "local":
        logger.info("使用本地 Embedding 模型：%s", settings.embedding_model_name)
        return BGEM3Embedder(model_name=settings.embedding_model_name)

    if provider == "doubao":
        logger.info("使用远程 Doubao Embedding API")
        return DoubaoEmbedder(
            api_key=settings.llm_api_key,
            base_url=settings.llm_api_base_url,
        )

    raise ValueError(
        f"未知的 EMBEDDING_PROVIDER: {provider!r}，有效值为 'local' 或 'doubao'"
    )
