import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from jobpilot_agent.api.schemas import (
    ErrorDetail,
    InterviewQuestion,
    JDClassification,
    JDRoutingRequest,
    JDRoutingResponse,
    JDRoutingResults,
    ResponseMetadata,
    ResumeAdviceItem,
)
from jobpilot_agent.graphs.jd_routing_graph import get_jd_routing_graph
from jobpilot_agent.logging_setup import bind_request_context, get_logger

router = APIRouter(tags=["JD Routing"])
log = get_logger(__name__)


def _build_classification(raw: dict) -> JDClassification:
    """将 classify_jd 节点输出的 dict 转为 JDClassification Pydantic 模型。

    若字段缺失或不合法，使用安全默认值。
    """
    defaults = {
        "job_type": "tech",
        "sub_type": "software_engineer",
        "level": "middle",
        "locale": "zh",
        "channel": "social",
    }
    merged = {**defaults, **{k: v for k, v in raw.items() if v}}
    try:
        return JDClassification(**merged)
    except Exception:  # noqa: BLE001
        return JDClassification(**defaults)


def _build_results(final_result: dict) -> JDRoutingResults:
    """将 final_synthesis 节点输出转为 JDRoutingResults Pydantic 模型。"""
    resume_advice = []
    for item in final_result.get("resume_advice") or []:
        try:
            resume_advice.append(ResumeAdviceItem(**item))
        except Exception:  # noqa: BLE001
            pass

    interview_questions = []
    for item in final_result.get("interview_questions") or []:
        try:
            interview_questions.append(InterviewQuestion(**item))
        except Exception:  # noqa: BLE001
            pass

    return JDRoutingResults(
        jd_summary=str(final_result.get("jd_summary") or ""),
        resume_advice=resume_advice,
        interview_questions=interview_questions,
    )


@router.post(
    "/jd-routing",
    response_model=JDRoutingResponse,
    summary="JD 路由分析",
    description=(
        "接收 JD 文本，通过 LangGraph 编排以下工作流：\n"
        "parse_jd → classify_jd → dispatch_skills → "
        "invoke_skills_parallel → merge_outputs → final_synthesis"
    ),
)
async def jd_routing(request: JDRoutingRequest) -> JDRoutingResponse | JSONResponse:
    start = time.monotonic()
    bind_request_context(request_id=request.request_id, user_id=request.user_id)
    log.info("jd_routing.start", jd_length=len(request.jd_text))

    try:
        graph = get_jd_routing_graph()

        initial_state = {
            "request_id": request.request_id,
            "user_id": request.user_id,
            "jd_text": request.jd_text,
            "user_context": request.user_context.model_dump(),
            "skill_outputs": [],
            "metadata": {},
            "errors": [],
        }

        final_state = await graph.ainvoke(initial_state)

        classification = _build_classification(final_state.get("classification") or {})
        results = _build_results(final_state.get("final_result") or {})

        invoked_skills: list[str] = final_state.get("invoked_skills") or []
        skipped_skills: list[str] = final_state.get("skipped_skills") or []

        # 从 metadata 读取 token 合计（各节点 + 各 Skill 之和）
        meta: dict = final_state.get("metadata") or {}
        total_tokens = sum(
            int(v.get("tokens") or 0)
            for v in meta.values()
            if isinstance(v, dict)
        )
        merge_meta = meta.get("merge_outputs") or {}
        total_tokens += int(merge_meta.get("total_skill_tokens") or 0)

        latency_ms = int((time.monotonic() - start) * 1000)

        response = JDRoutingResponse(
            request_id=request.request_id,
            classification=classification,
            invoked_skills=invoked_skills,
            skipped_skills=skipped_skills,
            results=results,
            metadata=ResponseMetadata(
                latency_ms=latency_ms,
                tokens_used=total_tokens or None,
                trace_id=request.request_id,
            ),
        )

        error_count = len(final_state.get("errors") or [])
        log.info(
            "jd_routing.complete",
            latency_ms=latency_ms,
            invoked_skills=invoked_skills,
            error_count=error_count,
        )
        return response

    except Exception as exc:  # noqa: BLE001
        log.exception("jd_routing.error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=ErrorDetail(
                error_code="INTERNAL_ERROR",
                error_message=str(exc),
            ).model_dump(),
        )
