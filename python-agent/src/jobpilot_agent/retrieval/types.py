"""核心数据类型。

所有 retrieval 层的输入/输出都通过这里定义的类型流通，
下游模块（skills, graphs）只应依赖这些类型，不应依赖具体实现。
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class CollectionName(str, Enum):
    """Milvus / Chroma 集合名称枚举。

    每个集合对应一类知识库：
    - JD_KB: JD（职位描述）知识库
    - INTERVIEW_KB: 面经知识库
    - USER_KB: 用户简历知识库
    """

    JD_KB = "jd_kb"
    INTERVIEW_KB = "interview_kb"
    USER_KB = "user_kb"


class Document(BaseModel):
    """统一的文档表示，是 retrieval 层处理的最小单元。

    Args:
        doc_id: 全局唯一标识，推荐格式 "{collection}-{source_id}-{chunk_idx}"。
        collection: 所属集合。
        text: 向量化与 BM25 的基础文本，切片后的内容。
        metadata: 附加元数据，用于标量过滤与结果溯源。
            推荐字段：
              - source_id: 原始文档 ID（如 "jd_0001" / "int_0001" / "user_resume"）
              - chunk_index: 切片序号（从 0 开始）
              - company: 公司名称（JD_KB / INTERVIEW_KB 适用）
              - position: 岗位名称
              - level: 职级（如 "senior" / "middle"）
              - stage: 面试阶段（INTERVIEW_KB 适用，如 "tech_qa"）
              - original_url: 来源 URL（可选）
        created_at: 文档入库时间（UTC）。

    Example:
        >>> doc = Document(
        ...     doc_id="jd_kb-jd_0001-0",
        ...     collection=CollectionName.JD_KB,
        ...     text="需要 3 年以上 Python 开发经验...",
        ...     metadata={"source_id": "jd_0001", "chunk_index": 0, "company": "字节跳动"},
        ... )
    """

    doc_id: str
    collection: CollectionName

    text: str

    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RetrievalResult(BaseModel):
    """单条检索结果，携带原始文档内容与多路得分信息。

    Args:
        doc_id: 对应 Document.doc_id。
        text: 文档正文，直接可用于 LLM prompt 组装。
        metadata: 原始元数据，透传自 Document.metadata。
        score: 最终融合得分（RRF / Weighted / Rerank 后的结果）。
        dense_score: 稠密向量相似度（COSINE），仅 Milvus/Chroma 召回阶段填充。
        sparse_score: BM25 原始得分，仅 BM25 召回阶段填充。
        rerank_score: Cross-Encoder 精排得分，仅 enable_rerank=True 时填充。
        rank_in_dense: 在 dense 召回列表中的排名（从 1 开始）。
        rank_in_sparse: 在 sparse 召回列表中的排名（从 1 开始）。
    """

    doc_id: str
    text: str
    metadata: dict[str, Any]

    score: float
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    rerank_score: Optional[float] = None

    rank_in_dense: Optional[int] = None
    rank_in_sparse: Optional[int] = None


class SearchOptions(BaseModel):
    """混合检索选项。

    Args:
        top_k: 最终返回结果数量，默认 5。
        filters: 标量过滤条件，如 {"company": "字节跳动", "stage": "tech_qa"}。
            Milvus 侧转为布尔表达式，BM25 侧按 substring 匹配。
        dense_weight: 加权融合时的 dense 权重。
            为 None（默认）时使用 RRF；同时指定 dense_weight 和 sparse_weight 则使用 WeightedRanker。
        sparse_weight: 加权融合时的 sparse 权重。
        dense_top_k: dense 召回候选池大小，默认 20。
        sparse_top_k: sparse 召回候选池大小，默认 20。
        enable_rerank: 是否启用 Cross-Encoder 精排，默认 False（耗时约 200ms）。
        rerank_top_k: 送入精排的候选数量，默认 10；精排后再截取 top_k。

    Example:
        >>> opts = SearchOptions(top_k=3, filters={"company": "字节跳动"}, enable_rerank=True)
    """

    top_k: int = 5
    filters: Optional[dict[str, Any]] = None

    dense_weight: Optional[float] = None
    sparse_weight: Optional[float] = None

    dense_top_k: int = 20
    sparse_top_k: int = 20

    enable_rerank: bool = False
    rerank_top_k: int = 10
