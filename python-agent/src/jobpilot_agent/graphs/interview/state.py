"""面试子图状态定义。

所有多节点写的字段都带自定义 reducer；current_stage 单节点写，无 reducer。
"""

from __future__ import annotations

from datetime import datetime
from operator import add
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

InterviewStage = Literal[
    "intro",
    "project_deep_dive",
    "tech_qa",
    "scenario",
    "reverse",
    "closing",
]


class Turn(BaseModel):
    """单轮对话记录"""

    turn_id: int
    role: Literal["interviewer", "candidate", "system"]
    content: str
    stage: InterviewStage
    created_at: datetime = Field(default_factory=datetime.utcnow)
    intent: str | None = None
    answer_points: list[str] = Field(default_factory=list)
    rag_source_doc_ids: list[str] = Field(default_factory=list)


class PerformanceSignal(BaseModel):
    """候选人单轮表现打分"""

    turn_id: int
    stage: InterviewStage
    dimension: Literal[
        "clarity",
        "technical_depth",
        "relevance",
        "problem_solving",
        "communication",
    ]
    score: float = Field(ge=0, le=10)
    evidence: str
    improvement_hint: str | None = None


class CandidateProfile(BaseModel):
    """候选人档案（从 user_kb RAG 检索构建）"""

    user_id: str
    resume_summary: str
    top_projects: list[str] = Field(default_factory=list)
    tech_strengths: list[str] = Field(default_factory=list)
    potential_weaknesses: list[str] = Field(default_factory=list)


class InterviewReport(BaseModel):
    """面试结束时的复盘报告"""

    stage_scores: dict[str, float] = Field(default_factory=dict)
    highlights: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    transcript_summary: str = ""


# ── Reducer 工具函数 ──────────────────────────────────────────────────────────


def _append_turns(left: list[Turn], right: list[Turn]) -> list[Turn]:
    """按 turn_id 去重追加，保证幂等性"""
    existing_ids = {t.turn_id for t in left}
    return left + [t for t in right if t.turn_id not in existing_ids]


def _dict_merge(left: dict[str, object], right: dict[str, object]) -> dict[str, object]:
    return {**left, **right}


def _inc_round(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    """stage_round_count 合并：同键累加"""
    out = dict(left)
    for k, v in right.items():
        out[k] = out.get(k, 0) + v
    return out


# ── 主状态 TypedDict ──────────────────────────────────────────────────────────


class InterviewState(TypedDict, total=False):
    # 会话身份（初始化后不变）
    session_id: str
    user_id: str
    company: str
    position: str
    level: str | None

    # 候选人档案（init_session 填）
    candidate_profile: dict[str, object]

    # 阶段推进
    current_stage: InterviewStage
    stage_history: Annotated[list[str], add]
    stage_round_count: Annotated[dict[str, int], _inc_round]

    # 对话记录
    transcript: Annotated[list[Turn], _append_turns]
    next_turn_id: int

    # 用户输入（由 interrupt 恢复时填）
    pending_user_input: str | None

    # 表现信号
    performance_signals: Annotated[list[PerformanceSignal], add]

    # 终节点输出
    report: dict[str, object] | None

    # 度量与错误
    metadata: Annotated[dict[str, object], _dict_merge]
    errors: Annotated[list[dict[str, object]], add]

    # 控制标志
    should_end_early: bool
