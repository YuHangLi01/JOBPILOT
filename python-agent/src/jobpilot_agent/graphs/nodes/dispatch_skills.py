"""dispatch_skills 节点：基于规则决定哪些 Skill 需要执行。

职责：
- 从 state 中重建 JDContext（包含 classification 和 parsed_jd）
- 调用 SkillDispatcher.dispatch(ctx) 获取 (invoked, skipped) 列表
- 写入 state["invoked_skills"] / state["skipped_skills"]
- 同时存储已构建的 JDContext dict 到 metadata，供 invoke_skills_parallel 复用

输入 state 字段：request_id, user_id, jd_text, user_context, parsed_jd, classification
输出 state 字段：invoked_skills, skipped_skills, metadata (dispatch_skills key)
"""

from __future__ import annotations

import time
from typing import Any

from jobpilot_agent.api.schemas import JDClassification, UserContext
from jobpilot_agent.graphs.state import JDRoutingState
from jobpilot_agent.logging_setup import get_logger
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.dispatcher import SkillDispatcher
from jobpilot_agent.skills.registry import register_all_skills

log = get_logger(__name__)


async def dispatch_skills(state: JDRoutingState) -> dict[str, Any]:
    """根据 JDContext 路由决策，返回需要执行的 Skill 名称列表。

    构建 JDContext 时：
    - user_context dict → UserContext Pydantic 模型（字段不匹配时使用默认值）
    - classification dict → JDClassification Pydantic 模型（字段不合法时节点已规整）

    Args:
        state: 当前图状态。

    Returns:
        state 增量字典：invoked_skills + skipped_skills + metadata。
    """
    start = time.monotonic()

    # ── 确保所有 Skill 已注册 ──────────────────────────────────────────
    register_all_skills()

    # ── 重建 JDContext ─────────────────────────────────────────────────
    user_ctx_raw: dict[str, Any] = state.get("user_context") or {}
    try:
        user_context = UserContext(**user_ctx_raw)
    except Exception:  # noqa: BLE001
        user_context = UserContext()

    classification_raw: dict[str, Any] = state.get("classification") or {}
    try:
        classification = JDClassification(**classification_raw)
    except Exception:  # noqa: BLE001
        classification = None

    ctx = JDContext(
        request_id=state.get("request_id", "unknown"),
        user_id=state.get("user_id", "unknown"),
        jd_text=state.get("jd_text", ""),
        user_context=user_context,
        classification=classification,
        parsed_jd=state.get("parsed_jd") or {},
        trace_id=state.get("request_id"),
    )

    # ── 路由决策 ──────────────────────────────────────────────────────
    dispatcher = SkillDispatcher()
    invoked_skills, skipped_skills = dispatcher.dispatch(ctx)

    invoked_names = [s.name for s in invoked_skills]
    skipped_names = [s.name for s in skipped_skills]

    log.info(
        "dispatch_skills.done",
        invoked=invoked_names,
        skipped=skipped_names,
    )

    return {
        "invoked_skills": invoked_names,
        "skipped_skills": skipped_names,
        "metadata": {
            "dispatch_skills": {
                "latency_ms": int((time.monotonic() - start) * 1000),
                "invoked_count": len(invoked_names),
                "skipped_count": len(skipped_names),
            }
        },
    }
