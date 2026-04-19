"""测试所有 Pydantic v2 Schema 的合法性与字段校验。"""

import pytest
from pydantic import ValidationError

from jobpilot_agent.api.schemas import (
    ErrorDetail,
    InterviewReport,
    InterviewResumeRequest,
    InterviewResumeResponse,
    InterviewStartRequest,
    InterviewStartResponse,
    InterviewStatusResponse,
    JDClassification,
    JDRoutingRequest,
    JDRoutingResponse,
    JDRoutingResults,
    NextAction,
    ResponseMetadata,
    ResumeAdviceItem,
    StageScore,
    UserContext,
)

# ── 公共 Schema ────────────────────────────────────────────────────────────────

def test_error_detail_valid() -> None:
    obj = ErrorDetail(error_code="INTERNAL_ERROR", error_message="something went wrong")
    assert obj.model_dump()["error_code"] == "INTERNAL_ERROR"


def test_response_metadata_valid() -> None:
    obj = ResponseMetadata(latency_ms=42)
    assert obj.latency_ms == 42
    assert obj.tokens_used is None


# ── JD Routing Schema ─────────────────────────────────────────────────────────

def test_jd_routing_request_valid() -> None:
    obj = JDRoutingRequest(
        request_id="req-001",
        user_id="u-001",
        jd_text="x" * 50,
    )
    assert obj.user_context.preferred_lang == "zh"


def test_jd_routing_request_jd_too_short() -> None:
    with pytest.raises(ValidationError):
        JDRoutingRequest(
            request_id="req-002",
            user_id="u-001",
            jd_text="too short",
        )


def test_jd_routing_request_jd_too_long() -> None:
    with pytest.raises(ValidationError):
        JDRoutingRequest(
            request_id="req-003",
            user_id="u-001",
            jd_text="x" * 10001,
        )


def test_jd_classification_valid() -> None:
    obj = JDClassification(
        job_type="tech",
        sub_type="backend",
        level="senior",
        locale="zh",
        channel="social",
    )
    assert obj.job_type == "tech"


def test_jd_routing_response_model_dump() -> None:
    resp = JDRoutingResponse(
        request_id="req-001",
        classification=JDClassification(
            job_type="tech", sub_type="backend", level="middle", locale="zh", channel="social"
        ),
        invoked_skills=["jd_parser"],
        skipped_skills=[],
        results=JDRoutingResults(jd_summary="A test summary"),
        metadata=ResponseMetadata(latency_ms=10),
    )
    data = resp.model_dump()
    assert data["request_id"] == "req-001"
    assert isinstance(data["results"]["resume_advice"], list)


def test_resume_advice_item_valid() -> None:
    obj = ResumeAdviceItem(priority="high", advice="Improve your resume")
    assert obj.priority == "high"


def test_user_context_defaults() -> None:
    ctx = UserContext()
    assert ctx.preferred_lang == "zh"
    assert ctx.user_kb_id is None


# ── Interview Schema ──────────────────────────────────────────────────────────

def test_interview_start_request_valid() -> None:
    obj = InterviewStartRequest(
        thread_id="t-001",
        user_id="u-001",
        company="TestCo",
        position="Engineer",
    )
    assert obj.context == {}


def test_next_action_valid() -> None:
    obj = NextAction(type="ask_question", content="Tell me about yourself", stage="intro")
    assert obj.type == "ask_question"


def test_interview_start_response_valid() -> None:
    obj = InterviewStartResponse(thread_id="t-001", state="waiting_user_input")
    assert obj.next_action is None


def test_interview_resume_request_valid() -> None:
    obj = InterviewResumeRequest(thread_id="t-001", user_input="My answer")
    assert obj.user_input == "My answer"


def test_stage_score_valid() -> None:
    obj = StageScore(stage="intro", score=8.5, comment="Good")
    assert obj.score == 8.5


def test_stage_score_out_of_range() -> None:
    with pytest.raises(ValidationError):
        StageScore(stage="intro", score=11.0, comment="Out of range")


def test_interview_report_valid() -> None:
    report = InterviewReport(
        stage_scores=[StageScore(stage="intro", score=7.0, comment="Ok")],
        highlights=["Clear communication"],
        improvements=["More depth"],
        transcript_summary="Overall good.",
    )
    assert len(report.stage_scores) == 1


def test_interview_resume_response_completed() -> None:
    obj = InterviewResumeResponse(state="completed", report=None)
    assert obj.state == "completed"


def test_interview_status_response_valid() -> None:
    obj = InterviewStatusResponse(thread_id="t-001", state="not_found")
    assert obj.transcript_length == 0
