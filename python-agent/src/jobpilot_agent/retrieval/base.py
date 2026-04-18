"""抽象基类，定义 retrieval 层对外的统一接口契约。

下游代码（skills, graphs）应依赖 BaseRetriever，不应直接依赖 HybridRetriever，
这样未来切换底层实现（如从 Milvus 切换到 Pinecone）时，下游代码零改动。
"""

from abc import ABC, abstractmethod

from jobpilot_agent.retrieval.types import CollectionName, Document, RetrievalResult, SearchOptions


class BaseRetriever(ABC):
    """检索器抽象基类。

    所有检索器实现（HybridRetriever、MockRetriever 等）都继承此类。
    对外暴露两个方法：search 和 add_documents。

    Example:
        >>> class MockRetriever(BaseRetriever):
        ...     async def search(self, query, collection, options=SearchOptions()):
        ...         return []
        ...     async def add_documents(self, collection, docs):
        ...         pass
    """

    @abstractmethod
    async def search(
        self,
        query: str,
        collection: CollectionName,
        options: SearchOptions = SearchOptions(),
    ) -> list[RetrievalResult]:
        """执行检索，返回排序后的结果列表。

        Args:
            query: 检索词，自然语言，可中英文混合。
            collection: 目标集合，决定从哪个知识库检索。
            options: 检索选项，控制 top_k、过滤条件、是否精排等。

        Returns:
            按 score 降序排列的检索结果，长度 <= options.top_k。
        """
        ...

    @abstractmethod
    async def add_documents(
        self,
        collection: CollectionName,
        docs: list[Document],
    ) -> None:
        """将文档批量写入检索索引。

        同时写入向量索引（Milvus / Chroma）和 BM25 内存索引。
        相同 doc_id 的文档会被覆盖（upsert 语义）。

        Args:
            collection: 目标集合。
            docs: 要写入的文档列表，每条必须有唯一 doc_id。
        """
        ...
