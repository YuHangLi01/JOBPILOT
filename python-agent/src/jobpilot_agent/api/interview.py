from fastapi import APIRouter
from fastapi.responses import JSONResponse

from jobpilot_agent.api.schemas import (
    ErrorDetail,
    InterviewReport,
    InterviewResumeRequest,
    InterviewResumeResponse,
    InterviewStartRequest,
    InterviewStartResponse,
    InterviewStatusResponse,
    NextAction,
    StageScore,
)
from jobpilot_agent.logging_setup import bind_request_context, get_logger

router = APIRouter(tags=["Interview"])
log = get_logger(__name__)


@router.post(
    "/interview/start",
    response_model=InterviewStartResponse,
    summary="开始面试会话（stub）",
)
async def interview_start(
    request: InterviewStartRequest,
) -> InterviewStartResponse | JSONResponse:
    bind_request_context(request_id=request.thread_id, user_id=request.user_id)
    log.info("interview.start", thread_id=request.thread_id, company=request.company)

    try:
        return InterviewStartResponse(
            thread_id=request.thread_id,
            state="waiting_user_input",
            next_action=NextAction(
                type="ask_question",
                content=(
                    f"你好！欢迎来到 {request.company} {request.position} 岗位的模拟面试。"
                    "请先做一个简短的自我介绍。"
                ),
                stage="intro",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("interview.start.error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=ErrorDetail(
                error_code="INTERNAL_ERROR",
                error_message=str(exc),
            ).model_dump(),
        )


@router.post(
    "/interview/resume",
    response_model=InterviewResumeResponse,
    summary="继续面试会话（stub）",
)
async def interview_resume(
    request: InterviewResumeRequest,
) -> InterviewResumeResponse | JSONResponse:
    bind_request_context(request_id=request.thread_id)
    log.info("interview.resume", thread_id=request.thread_id)

    try:
        # Stub：根据输入长度模拟面试结束
        if len(request.user_input) > 200:  # noqa: PLR2004
            return InterviewResumeResponse(
                state="completed",
                next_action=NextAction(
                    type="end",
                    content="感谢参与模拟面试，面试已结束，以下是评估报告。",
                    stage="closing",
                ),
                report=InterviewReport(
                    stage_scores=[
                        StageScore(stage="intro", score=8.0, comment="自我介绍清晰"),
                        StageScore(stage="tech_qa", score=7.5, comment="技术回答有深度"),
                    ],
                    highlights=["表达清晰", "有实际项目经验"],
                    improvements=["可进一步量化成果", "系统设计可更结构化"],
                    transcript_summary="候选人整体表现良好，建议进入下一轮。",
                ),
            )
        return InterviewResumeResponse(
            state="waiting_user_input",
            next_action=NextAction(
                type="ask_question",
                content="请描述你最有挑战性的一个项目经历，以及你的具体贡献。",
                stage="project_deep_dive",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("interview.resume.error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=ErrorDetail(
                error_code="INTERNAL_ERROR",
                error_message=str(exc),
            ).model_dump(),
        )


@router.get(
    "/interview/{thread_id}/status",
    response_model=InterviewStatusResponse,
    summary="查询面试会话状态（stub）",
)
async def interview_status(thread_id: str) -> InterviewStatusResponse | JSONResponse:
    bind_request_context(request_id=thread_id)
    log.info("interview.status", thread_id=thread_id)

    try:
        return InterviewStatusResponse(
            thread_id=thread_id,
            state="waiting_user_input",
            current_stage="intro",
            last_checkpoint_at=None,
            transcript_length=0,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("interview.status.error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=ErrorDetail(
                error_code="INTERNAL_ERROR",
                error_message=str(exc),
            ).model_dump(),
        )
