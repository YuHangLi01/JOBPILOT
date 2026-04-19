"""kb_builder 内部 Pydantic 模型。

分两类：
1. **Input 侧**：`LabeledJD` / `StructuredInterview` / `InterviewTurn`
   —— 严格对齐 P2.1 产出的 JSONL 行格式。
2. **Chunk 侧**：`JDChunk` / `InterviewChunk` / `UserChunk`
   —— splitter 输出的中间产物，再由 orchestrator 转成 `jobpilot_agent.retrieval.types.Document`
   并写入 Milvus。

Chunk 上的字段顺序与 Milvus 动态字段名保持一致，便于后续检索过滤。
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Input 侧：labeled / clean JSONL
# ---------------------------------------------------------------------------


class JDLabels(BaseModel):
    job_type: str
    sub_type: str
    level: str
    locale: str
    channel: str


class LabeledJD(BaseModel):
    """`knowledge-base/data/labeled/jd_labeled.jsonl` 的一行。"""

    model_config = ConfigDict(extra="ignore")

    jd_id: str
    jd_text: str
    labels: JDLabels


class InterviewTurn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    turn_id: int
    role: Literal["interviewer", "candidate"]
    content: str
    stage: str


class StructuredInterview(BaseModel):
    """`knowledge-base/data/clean/interview_structured_filtered.jsonl` 的一行。"""

    model_config = ConfigDict(extra="ignore")

    interview_id: str
    company: str = "unknown"
    position: str = ""
    level: Optional[str] = None
    year: Optional[int] = None
    turns: list[InterviewTurn] = Field(default_factory=list)
    outcome: str = "unknown"


# ---------------------------------------------------------------------------
# Chunk 侧：splitter 产出的中间态
# ---------------------------------------------------------------------------


JDChunkType = Literal["responsibilities", "requirements", "perks", "full"]


class JDChunk(BaseModel):
    """JD 切片后的单个文档。"""

    doc_id: str
    text: str

    # 结构化字段（Milvus explicit schema 字段）
    source_id: str
    chunk_index: int
    company: str = ""
    position: str = ""

    # 动态字段
    chunk_type: JDChunkType
    location: str = ""
    job_type: str
    sub_type: str
    level: str
    locale: str
    channel: str


class InterviewChunk(BaseModel):
    """面经切片（按 turn 粒度）。"""

    doc_id: str
    text: str

    source_id: str
    chunk_index: int
    company: str = ""
    position: str = ""

    role: Literal["interviewer", "candidate"]
    stage: str
    level: Optional[str] = None
    year: Optional[int] = None
    outcome: str = "unknown"

    prev_turn_text: str = ""
    next_turn_text: str = ""


UserSection = Literal["basic", "education", "work_experience", "projects", "skills", "other"]


class UserChunk(BaseModel):
    """用户简历切片（按 H2/H3 Markdown 小节）。"""

    doc_id: str
    text: str

    source_id: str
    chunk_index: int

    user_id: str
    doc_type: Literal["resume", "portfolio_item"] = "resume"
    section: UserSection
    section_title: str


# ---------------------------------------------------------------------------
# 统计报告
# ---------------------------------------------------------------------------


class ChunksPerDocStats(BaseModel):
    mean: float
    median: float
    min: int
    max: int


class IngestReport(BaseModel):
    collection: str
    total_docs: int
    total_chunks: int
    chunks_per_doc_stats: ChunksPerDocStats
    embedding_upsert_time_sec: float
    bm25_save_time_sec: float
    failed_docs: list[str] = Field(default_factory=list)
