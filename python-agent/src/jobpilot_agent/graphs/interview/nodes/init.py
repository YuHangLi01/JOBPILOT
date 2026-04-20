"""init_session 节点：初始化会话，构建候选人档案。"""

from __future__ import annotations

from datetime import datetime

from jobpilot_agent.graphs.interview.profile_builder import build_candidate_profile
from jobpilot_agent.graphs.interview.state import InterviewState
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


async def init_session_node(state: InterviewState) -> dict[str, object]:
    """初始化面试会话。

    职责：
    - 从 user_kb 构建候选人档案（RAG 检索）
    - 若存在 source_session_context（主图产出），将 JD 摘要带入检索上下文
    - 设置 current_stage = intro
    - 记录会话开始时间
    """
    user_id = str(state.get("user_id", ""))
    company = str(state.get("company", ""))
    position = str(state.get("position", ""))

    # 从 API 层通过 metadata 传入的主图 session context
    source_ctx: dict = (state.get("metadata") or {}).get("source_session_context") or {}

    jd_context: dict = {
        "company": company,
        "position": position,
        "jd_summary": source_ctx.get("jd_summary", ""),
        "parsed_jd": source_ctx.get("parsed_jd", {}),
    }

    profile = await build_candidate_profile(
        user_id=user_id,
        jd_context=jd_context,
    )

    log.info(
        "init_session_node.done",
        user_id=user_id,
        company=company,
        has_source_context=bool(source_ctx),
    )
    return {
        "candidate_profile": profile.model_dump(),
        "current_stage": "intro",
        "transcript": [],
        "stage_history": [],
        "performance_signals": [],
        "stage_round_count": {},
        "errors": [],
        "metadata": {
            "session_started_at": datetime.utcnow().isoformat(),
            "company": company,
            "position": position,
            "has_source_context": bool(source_ctx),
            "source_session_context": source_ctx,
        },
    }
