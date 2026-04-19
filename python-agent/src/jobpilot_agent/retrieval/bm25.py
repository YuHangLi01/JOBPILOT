"""BM25 稀疏检索索引。

设计说明：
- 内存索引，数据量 500~3000 条时性能完全够用
- 使用 rank_bm25.BM25Okapi + jieba 中文分词
- 支持 metadata 标量过滤（substring 匹配，中文语义容错）
- pickle 持久化，进程启动时加载，入库后整体重建
- 空索引（docs=[]）时安全返回 []，不崩溃
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Optional

from jobpilot_agent.retrieval.tokenizer import tokenize_for_bm25
from jobpilot_agent.retrieval.types import CollectionName, Document, RetrievalResult

logger = logging.getLogger(__name__)


class BM25Index:
    """单个 Collection 的内存 BM25 索引。

    每个 CollectionName 对应一个独立实例，由 HybridRetriever 管理生命周期。

    Args:
        collection: 所属集合，用于日志与持久化文件命名。

    Example:
        >>> index = BM25Index(CollectionName.JD_KB)
        >>> docs = [Document(doc_id="jd-0", collection=CollectionName.JD_KB,
        ...                  text="Python 后端工程师", metadata={"company": "字节跳动"})]
        >>> index.build(docs)
        >>> results = index.search("Python 后端", top_k=3)
        >>> assert len(results) <= 3
    """

    def __init__(self, collection: CollectionName) -> None:
        self.collection = collection
        self._docs: list[Document] = []
        self._bm25: Any = None  # rank_bm25.BM25Okapi，运行时才导入
        self._doc_tokens: list[list[str]] = []

    # ------------------------------------------------------------------
    # 索引管理
    # ------------------------------------------------------------------

    def build(self, docs: list[Document]) -> None:
        """全量重建 BM25 索引。

        对于 500 条以内的数据量，全量重建比增量更新更简单且开销可接受。
        空列表入参时安全处理（不崩溃，search 直接返回 []）。

        Args:
            docs: 文档列表，text 字段将被分词后构建索引。
        """
        if not docs:
            self._docs = []
            self._doc_tokens = []
            self._bm25 = None
            logger.debug("[BM25/%s] 索引重建：docs=0，索引置空", self.collection.value)
            return

        from rank_bm25 import BM25Okapi  # type: ignore[import]

        self._docs = list(docs)
        self._doc_tokens = [tokenize_for_bm25(d.text) for d in docs]
        self._bm25 = BM25Okapi(self._doc_tokens)
        logger.debug(
            "[BM25/%s] 索引重建完成：docs=%d", self.collection.value, len(docs)
        )

    def add_or_update(self, new_docs: list[Document]) -> None:
        """增量更新：合并新文档后全量重建。

        相同 doc_id 的文档会被新版本覆盖。

        Args:
            new_docs: 需要新增或更新的文档列表。
        """
        existing = {d.doc_id: d for d in self._docs}
        for doc in new_docs:
            existing[doc.doc_id] = doc
        self.build(list(existing.values()))

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = 20,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[RetrievalResult]:
        """BM25 关键词检索。

        流程：
        1. 对 query 分词
        2. BM25Okapi 打分
        3. 应用 metadata 标量过滤（substring 匹配）
        4. 按分数降序，相同分数按 doc_id 字典序（稳定排序）
        5. 截取 top_k

        Args:
            query: 检索词。
            top_k: 返回结果数量上限。
            filters: 过滤条件，如 {"company": "字节"}。
                支持 substring 匹配（不区分大小写），例如：
                - {"company": "字节"} 会匹配 metadata.company="字节跳动"
                - {"stage": "tech_qa"} 精确匹配
            (注：为保持中文语义容错，统一用 substring，不做精确匹配)

        Returns:
            按 sparse_score 降序排列的 RetrievalResult 列表。
        """
        if self._bm25 is None or not self._docs:
            return []

        query_tokens = tokenize_for_bm25(query)
        if not query_tokens:
            return []

        raw_scores: list[float] = self._bm25.get_scores(query_tokens).tolist()

        # 组装候选，同时进行过滤
        candidates: list[tuple[float, str, int]] = []  # (score, doc_id, idx)
        for idx, (doc, score) in enumerate(zip(self._docs, raw_scores)):
            if filters and not _match_filters(doc.metadata, filters):
                continue
            candidates.append((score, doc.doc_id, idx))

        # 稳定排序：先按 score 降序，再按 doc_id 字典序（保证确定性）
        candidates.sort(key=lambda x: (-x[0], x[1]))

        results: list[RetrievalResult] = []
        for rank, (score, _doc_id, idx) in enumerate(candidates[:top_k], start=1):
            doc = self._docs[idx]
            results.append(
                RetrievalResult(
                    doc_id=doc.doc_id,
                    text=doc.text,
                    metadata=doc.metadata,
                    score=score,
                    sparse_score=score,
                    rank_in_sparse=rank,
                )
            )

        return results

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """将索引序列化到文件（pickle）。

        Args:
            path: 目标文件路径，父目录不存在时自动创建。
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("wb") as f:
            pickle.dump(
                {
                    "docs": self._docs,
                    "doc_tokens": self._doc_tokens,
                    "bm25": self._bm25,
                    "collection": self.collection,
                },
                f,
                protocol=pickle.HIGHEST_PROTOCOL,
            )
        logger.info("[BM25/%s] 索引已保存到 %s", self.collection.value, p)

    @classmethod
    def load(cls, path: str | Path) -> "BM25Index":
        """从 pickle 文件加载索引。

        Args:
            path: 索引文件路径。

        Returns:
            恢复的 BM25Index 实例。

        Raises:
            FileNotFoundError: 文件不存在时。
        """
        p = Path(path)
        with p.open("rb") as f:
            data = pickle.load(f)  # noqa: S301

        instance = cls(collection=data["collection"])
        instance._docs = data["docs"]
        instance._doc_tokens = data["doc_tokens"]
        instance._bm25 = data["bm25"]
        logger.info(
            "[BM25/%s] 索引已从 %s 加载，docs=%d",
            instance.collection.value,
            p,
            len(instance._docs),
        )
        return instance

    # ------------------------------------------------------------------
    # 实用
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._docs)

    def __repr__(self) -> str:
        return (
            f"BM25Index(collection={self.collection.value!r}, docs={len(self._docs)})"
        )


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _match_filters(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    """检查 metadata 是否满足所有过滤条件。

    匹配策略：substring + 不区分大小写，中文语义容错。
    例如 filters={"company": "字节"} 会匹配 metadata["company"]="字节跳动"。

    Args:
        metadata: 文档元数据。
        filters: 过滤条件字典。

    Returns:
        True 表示满足全部条件（AND 逻辑）。
    """
    for key, value in filters.items():
        meta_val = metadata.get(key)
        if meta_val is None:
            return False
        # 统一转字符串后做 substring 匹配
        if str(value).lower() not in str(meta_val).lower():
            return False
    return True
