"""
JobPilot Agent — Pydantic v2 API Schemas

所有字段均为 Pydantic v2 语法（model_dump / model_validate）。
下周将由 openapi-typescript 自动生成对应的 TypeScript 类型替换 Node 侧的手写版本。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ================================================================
# 公共模型
# ================================================================


class ErrorDetail(BaseModel):
    error_code: Literal[
        "INTERNAL_ERROR",
        "LLM_RATE_LIMITED",
        "LLM_TIMEOUT",
        "SKILL_TIMEOUT",
        "RAG_EMPTY",
        "INVALID_INPUT",
        "STATE_NOT_FOUND",
    ]
    error_message: str
    partial_results: dict[str, object] | None = None


class ResponseMetadata(BaseModel):
    latency_ms: int
    tokens_used: int | None = None
    trace_id: str | None = None


# ================================================================
# JD 路由
# ================================================================


class UserContext(BaseModel):
    user_kb_id: str | None = None
    preferred_lang: Literal["zh", "en"] = "zh"
    github_username: str | None = None
    portfolio_doc_ref: str | None = None  # 飞书云文档 doc_token
    feishu_chat_id: str | None = None


class JDRoutingRequest(BaseModel):
    request_id: str
    user_id: str
    jd_text: str = Field(min_length=50, max_length=10000)
    user_context: UserContext = Field(default_factory=UserContext)


class JDClassification(BaseModel):
    job_type: Literal["tech", "product", "design", "ops", "mgmt"]
    sub_type: str
    level: Literal["junior", "middle", "senior", "lead"]
    locale: Literal["zh", "en"]
    channel: Literal["social", "campus"]


class InterviewQuestion(BaseModel):
    question: str
    intent: str
    answer_points: list[str]


class ResumeAdviceItem(BaseModel):
    priority: Literal["high", "medium", "low"]
    advice: str
    related_jd_requirement: str | None = None


class InterviewInvitation(BaseModel):
    should_invite: bool
    reason: str | None = None
    suggested_company: str | None = None
    suggested_position: str | None = None
    cta_text: str = "开始模拟面试"
    session_seed: dict = Field(default_factory=dict)


class JDRoutingResults(BaseModel):
    jd_summary: str
    resume_advice: list[ResumeAdviceItem] = Field(default_factory=list)
    interview_questions: list[InterviewQuestion] = Field(default_factory=list)
    interview_invitation: InterviewInvitation | None = None


class JDRoutingResponse(BaseModel):
    request_id: str
    classification: JDClassification
    invoked_skills: list[str]
    skipped_skills: list[str]
    results: JDRoutingResults
    metadata: ResponseMetadata


# ================================================================
# 面试（Interview）
# ================================================================


class InterviewStartRequest(BaseModel):
    thread_id: str
    user_id: str
    company: str | None = None
    position: str | None = None
    context: dict[str, object] = Field(default_factory=dict)


class NextAction(BaseModel):
    type: Literal["ask_question", "wait", "end"]
    content: str
    stage: Literal[
        "intro",
        "project_deep_dive",
        "tech_qa",
        "scenario",
        "reverse",
        "closing",
    ]


class InterviewStartResponse(BaseModel):
    thread_id: str
    state: Literal["waiting_user_input", "completed", "error"]
    next_action: NextAction | None = None


class InterviewResumeRequest(BaseModel):
    thread_id: str
    user_input: str


class StageScore(BaseModel):
    stage: str
    score: float = Field(ge=0, le=10)
    comment: str


class InterviewReport(BaseModel):
    stage_scores: list[StageScore]
    highlights: list[str]
    improvements: list[str]
    transcript_summary: str


class InterviewResumeResponse(BaseModel):
    state: Literal["waiting_user_input", "completed", "error"]
    next_action: NextAction | None = None
    report: InterviewReport | None = None


class InterviewStatusResponse(BaseModel):
    thread_id: str
    state: Literal["waiting_user_input", "completed", "not_found"]
    current_stage: str | None = None
    last_checkpoint_at: datetime | None = None
    transcript_length: int = 0
