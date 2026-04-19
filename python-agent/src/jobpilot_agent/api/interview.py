from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from langgraph.types import Command, StateSnapshot
from pydantic import BaseModel

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
from jobpilot_agent.graphs.interview.interview_subgraph import get_interview_subgraph
from jobpilot_agent.logging_setup import bind_request_context, get_logger

router = APIRouter(tags=["Interview"])
log = get_logger(__name__)


# ── 辅助函数 ────────────────────────────────────────────────────────────────


def _serialize(value: Any) -> Any:
    """递归序列化 state 中的 Pydantic models / datetime / list / dict。"""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _extract_next_action(snapshot: StateSnapshot) -> NextAction | None:
    """从 StateSnapshot 提取 interrupt payload，构建 NextAction。"""
    if not snapshot.interrupts:
        return None
    payload: dict[str, Any] = snapshot.interrupts[0].value
    # snapshot.next[0] 是被中断的节点名，与 InterviewStage 一致
    stage = snapshot.next[0] if snapshot.next else "intro"
    return NextAction(
        type=payload.get("type", "ask_question"),
        content=str(payload.get("content", "")),
        stage=stage,  # type: ignore[arg-type]
    )


def _to_api_report(report_dict: dict[str, Any]) -> InterviewReport:
    """把 state 层 {stage: score} dict 转换为 API 层 list[StageScore]。"""
    stage_scores = [
        StageScore(stage=k, score=float(v), comment="")
        for k, v in report_dict.get("stage_scores", {}).items()
        if float(v) >= 0  # LLM uses -1 for unvisited stages; omit from API response
    ]
    return InterviewReport(
        stage_scores=stage_scores,
        highlights=report_dict.get("highlights", []),
        improvements=report_dict.get("improvements", []),
        transcript_summary=str(report_dict.get("transcript_summary", "")),
    )


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.post(
    "/interview/start",
    response_model=InterviewStartResponse,
    summary="开始面试会话",
)
async def interview_start(
    request: InterviewStartRequest,
) -> InterviewStartResponse | JSONResponse:
    bind_request_context(request_id=request.thread_id, user_id=request.user_id)
    log.info("interview.start", thread_id=request.thread_id, company=request.company)

    try:
        graph = get_interview_subgraph()
        config = {"configurable": {"thread_id": request.thread_id}}

        initial_state = {
            "session_id": request.thread_id,
            "user_id": request.user_id,
            "company": request.company,
            "position": request.position,
            "transcript": [],
            "stage_history": [],
            "stage_round_count": {},
            "performance_signals": [],
            "metadata": {},
            "errors": [],
        }

        await graph.ainvoke(initial_state, config=config)
        snapshot: StateSnapshot = await graph.aget_state(config)
        next_action = _extract_next_action(snapshot)

        return InterviewStartResponse(
            thread_id=request.thread_id,
            state="waiting_user_input" if next_action else "completed",
            next_action=next_action,
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
    summary="继续面试会话",
)
async def interview_resume(
    request: InterviewResumeRequest,
) -> InterviewResumeResponse | JSONResponse:
    bind_request_context(request_id=request.thread_id)
    log.info("interview.resume", thread_id=request.thread_id)

    try:
        graph = get_interview_subgraph()
        config = {"configurable": {"thread_id": request.thread_id}}

        # 检查 thread 是否存在
        snapshot: StateSnapshot = await graph.aget_state(config)
        if not snapshot or not snapshot.values:
            raise HTTPException(
                status_code=404,
                detail=f"Thread {request.thread_id} not found",
            )

        # 用 Command(resume=...) 恢复执行
        await graph.ainvoke(Command(resume=request.user_input), config=config)
        snapshot = await graph.aget_state(config)

        if snapshot.next == ():  # 图跑完
            report_dict: dict[str, Any] = snapshot.values.get("report") or {}
            return InterviewResumeResponse(
                state="completed",
                report=_to_api_report(report_dict),
            )

        next_action = _extract_next_action(snapshot)
        return InterviewResumeResponse(
            state="waiting_user_input",
            next_action=next_action,
        )

    except HTTPException:
        raise
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
    "/interview/{thread_id}/_debug_state",
    summary="调试端点：返回完整 LangGraph state（仅 dev/staging 环境）",
    include_in_schema=False,
)
async def debug_state(thread_id: str) -> dict[str, Any]:
    from jobpilot_agent.config import get_settings

    settings = get_settings()
    if settings.app_env == "prod":
        raise HTTPException(status_code=403, detail="Not allowed in production")

    graph = get_interview_subgraph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot: StateSnapshot = await graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")

    return {
        "values": _serialize(dict(snapshot.values)),
        "next": list(snapshot.next),
        "interrupts": (
            [{"value": _serialize(i.value)} for i in snapshot.interrupts]
            if snapshot.interrupts
            else []
        ),
        "created_at": snapshot.created_at if snapshot.created_at else None,
    }


@router.get(
    "/interview/{thread_id}/status",
    response_model=InterviewStatusResponse,
    summary="查询面试会话状态",
)
async def interview_status(thread_id: str) -> InterviewStatusResponse | JSONResponse:
    bind_request_context(request_id=thread_id)
    log.info("interview.status", thread_id=thread_id)

    try:
        graph = get_interview_subgraph()
        config = {"configurable": {"thread_id": thread_id}}

        snapshot: StateSnapshot = await graph.aget_state(config)
        if not snapshot or not snapshot.values:
            return InterviewStatusResponse(
                thread_id=thread_id,
                state="not_found",
            )

        is_completed = snapshot.next == ()
        return InterviewStatusResponse(
            thread_id=thread_id,
            state="completed" if is_completed else "waiting_user_input",
            current_stage=snapshot.values.get("current_stage"),
            last_checkpoint_at=(
                datetime.fromisoformat(snapshot.created_at)
                if snapshot.created_at
                else None
            ),
            transcript_length=len(snapshot.values.get("transcript", [])),
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
