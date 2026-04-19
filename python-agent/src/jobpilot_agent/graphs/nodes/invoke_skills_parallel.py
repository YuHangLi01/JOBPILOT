"""invoke_skills_parallel 节点：并行执行所有被路由到的 Skill。

职责：
- 重建 JDContext（与 dispatch_skills 节点相同逻辑）
- 从 SkillRegistry 按 invoked_skills 名称列表获取 Skill 实例
- 使用 asyncio.gather(..., return_exceptions=True) 并行执行所有 Skill
- 每个 Skill 的输出（SkillOutput）序列化为 dict 追加到 skill_outputs
- 若某个 Skill 抛出原生异常（理论上不应发生），安全降级并记录到 errors

输入 state 字段：invoked_skills, request_id, user_id, jd_text, user_context,
                  parsed_jd, classification
输出 state 字段：skill_outputs (累积), errors (累积), metadata (invoke_skills_parallel key)
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from jobpilot_agent.api.schemas import JDClassification, UserContext
from jobpilot_agent.graphs.state import JDRoutingState
from jobpilot_agent.logging_setup import get_logger
from jobpilot_agent.skills.base import SkillOutput
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.registry import registry

log = get_logger(__name__)


def _rebuild_ctx(state: JDRoutingState) -> JDContext:
    """从图状态重建 JDContext，供并行 Skill 共享（只读）。"""
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

    return JDContext(
        request_id=state.get("request_id", "unknown"),
        user_id=state.get("user_id", "unknown"),
        jd_text=state.get("jd_text", ""),
        user_context=user_context,
        classification=classification,
        parsed_jd=state.get("parsed_jd") or {},
        trace_id=state.get("request_id"),
    )


async def invoke_skills_parallel(state: JDRoutingState) -> dict[str, Any]:
    """并行执行 invoked_skills 列表中的所有 Skill。

    关键设计：
    - asyncio.gather(return_exceptions=True) 确保单个 Skill 失败不中断其他 Skill
    - 每个 Skill 本身已保证 invoke() 不抛原生异常（SkillOutput(success=False)）
    - 若 Skill 不存在于 registry，生成一个失败 SkillOutput 占位

    Args:
        state: 当前图状态。

    Returns:
        state 增量字典：skill_outputs（SkillOutput dict 列表）+ errors + metadata。
    """
    start = time.monotonic()
    invoked_names: list[str] = state.get("invoked_skills") or []

    if not invoked_names:
        return {
            "skill_outputs": [],
            "metadata": {
                "invoke_skills_parallel": {
                    "latency_ms": 0,
                    "skill_count": 0,
                }
            },
        }

    ctx = _rebuild_ctx(state)

    # ── 收集 Skill 实例 ────────────────────────────────────────────────
    skills_to_run = []
    missing_skills = []
    for name in invoked_names:
        skill = registry.get(name)
        if skill is not None:
            skills_to_run.append(skill)
        else:
            log.warning("invoke_skills_parallel.skill_not_found", name=name)
            missing_skills.append(name)

    # ── 并行执行（每个 Skill 最多 30 秒超时）────────────────────────
    _SKILL_TIMEOUT = 30.0

    async def _invoke_with_timeout(skill: Any) -> SkillOutput:
        try:
            return await asyncio.wait_for(skill.invoke(ctx), timeout=_SKILL_TIMEOUT)
        except asyncio.TimeoutError:
            log.warning("invoke_skills_parallel.skill_timeout", skill=skill.name, timeout=_SKILL_TIMEOUT)
            return SkillOutput.make_error(
                skill_name=skill.name,
                error_code="SKILL_TIMEOUT",
                message=f"Skill timed out after {_SKILL_TIMEOUT}s",
                latency_ms=int(_SKILL_TIMEOUT * 1000),
            )

    results = await asyncio.gather(
        *[_invoke_with_timeout(s) for s in skills_to_run],
        return_exceptions=True,
    )

    # ── 处理结果 ──────────────────────────────────────────────────────
    skill_outputs: list[dict[str, Any]] = []
    new_errors: list[dict[str, Any]] = []

    for skill, result in zip(skills_to_run, results):
        if isinstance(result, Exception):
            # Skill 违反约定抛了原生异常，安全降级
            log.error(
                "invoke_skills_parallel.skill_raised_exception",
                skill=skill.name,
                error=str(result),
                exc_info=result,
            )
            output = SkillOutput.make_error(
                skill_name=skill.name,
                error_code="SKILL_ERROR",
                message=str(result),
                latency_ms=int((time.monotonic() - start) * 1000),
            )
            new_errors.append({"skill": skill.name, "error": str(result)})
        else:
            output = result  # type: ignore[assignment]
            if not output.success:
                new_errors.append({"skill": skill.name, "error": output.error})

        skill_outputs.append(output.model_dump())

    # 为缺失 Skill 生成占位失败输出
    for name in missing_skills:
        skill_outputs.append(
            SkillOutput.make_error(
                skill_name=name,
                error_code="SKILL_NOT_FOUND",
                message=f"Skill '{name}' not found in registry",
            ).model_dump()
        )
        new_errors.append({"skill": name, "error": "Skill not found in registry"})

    latency = int((time.monotonic() - start) * 1000)
    log.info(
        "invoke_skills_parallel.done",
        total=len(skill_outputs),
        success=sum(1 for o in skill_outputs if o.get("success")),
        latency_ms=latency,
    )

    result_dict: dict[str, Any] = {
        "skill_outputs": skill_outputs,
        "metadata": {
            "invoke_skills_parallel": {
                "latency_ms": latency,
                "skill_count": len(skill_outputs),
            }
        },
    }
    if new_errors:
        result_dict["errors"] = new_errors
    return result_dict
