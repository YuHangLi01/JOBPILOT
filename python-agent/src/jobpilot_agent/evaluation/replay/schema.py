"""Replay 评估数据结构。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReplayPair(BaseModel):
    """单个「历史 → 真实追问」评估对。"""

    interview_id: str
    pair_id: str  # f"{interview_id}-{turn_id}"

    company: str
    position: str
    stage: str

    history_turns_raw: list[dict[str, object]]  # 原始 turn dicts（含 turn_id/role/content/stage）
    history_text: str  # 格式化后的历史对话（供日志与报告展示）

    real_next_question: str  # ground truth
    real_next_intent: str | None = None


class ReplayResult(BaseModel):
    """单对的评估结果。"""

    pair_id: str
    stage: str

    bot_next_question: str
    bot_top_k_questions: list[str] = Field(default_factory=list)

    # 相似度指标
    semantic_similarity: float = 0.0  # cosine(embed(bot), embed(real))

    # rank 指标（1-based；miss = 99）
    rank_in_top_k: int = 99
    in_top_3: bool = False
    in_top_5: bool = False

    # 度量
    latency_ms: int = 0
    tokens_used: int = 0
    error: str | None = None


class StageMetrics(BaseModel):
    """某阶段的汇总指标。"""

    count: int
    mean_similarity: float
    rank_at_3: float


class ReplayAggregateMetrics(BaseModel):
    """所有 Pair 的汇总指标。"""

    total_pairs: int
    successful_pairs: int

    mean_similarity: float
    median_similarity: float

    rank_at_3: float
    rank_at_5: float

    per_stage: dict[str, StageMetrics] = Field(default_factory=dict)
    per_company: dict[str, StageMetrics] = Field(default_factory=dict)

    similarity_distribution: dict[str, int] = Field(default_factory=dict)
