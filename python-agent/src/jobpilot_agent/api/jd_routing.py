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
from jobpilot_agent.logging_setup import bind_request_context, get_logger

router = APIRouter(tags=["JD Routing"])
log = get_logger(__name__)


@router.post(
    "/jd-routing",
    response_model=JDRoutingResponse,
    summary="JD 路由分析（stub）",
    description="接收 JD 文本，触发 LangGraph 编排工作流（当前为 stub 实现，返回示例数据）。",
)
async def jd_routing(request: JDRoutingRequest) -> JDRoutingResponse | JSONResponse:
    start = time.monotonic()
    bind_request_context(request_id=request.request_id, user_id=request.user_id)
    log.info("jd_routing.start", jd_length=len(request.jd_text))

    try:
        # ── Stub 实现：返回合法的示例 Response ────────────────────────────
        result = JDRoutingResponse(
            request_id=request.request_id,
            classification=JDClassification(
                job_type="tech",
                sub_type="backend_engineer",
                level="middle",
                locale="zh",
                channel="social",
            ),
            invoked_skills=["jd_parser", "resume_advisor", "interview_generator"],
            skipped_skills=[],
            results=JDRoutingResults(
                jd_summary=(
                    "该岗位为后端工程师，要求熟悉 Python / TypeScript，"
                    "有分布式系统经验，负责核心服务研发与架构演进。"
                ),
                resume_advice=[
                    ResumeAdviceItem(
                        priority="high",
                        advice="突出分布式系统设计经验，量化系统规模与优化收益。",
                        related_jd_requirement="熟悉分布式架构",
                    ),
                    ResumeAdviceItem(
                        priority="medium",
                        advice="补充 LangChain / LangGraph 项目经验。",
                        related_jd_requirement="AI Agent 开发经验优先",
                    ),
                ],
                interview_questions=[
                    InterviewQuestion(
                        question="请描述一次你主导的分布式系统设计，遇到了哪些挑战？",
                        intent="考察系统设计能力与实际落地经验",
                        answer_points=[
                            "说明业务背景与规模",
                            "列举技术选型理由",
                            "说明遇到的问题及解决方案",
                            "量化结果",
                        ],
                    ),
                ],
            ),
            metadata=ResponseMetadata(
                latency_ms=int((time.monotonic() - start) * 1000),
                tokens_used=None,
                trace_id=request.request_id,
            ),
        )

        log.info("jd_routing.complete", latency_ms=result.metadata.latency_ms)
        return result

    except Exception as exc:  # noqa: BLE001
        log.exception("jd_routing.error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content=ErrorDetail(
                error_code="INTERNAL_ERROR",
                error_message=str(exc),
            ).model_dump(),
        )
