"""Skill 层调试端点。

这些端点仅供开发与演示使用，帮助快速验证：
1. 哪些 Skill 已注册及其元信息
2. 给定 JDContext 时各 Skill 的路由决策
3. 直接触发某个 Skill 执行（无需走完整 LangGraph 流程）

URL 前缀：/api/v1/skills（在 main.py 注册时加 prefix）
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jobpilot_agent.api.schemas import JDClassification, UserContext
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.dispatcher import SkillDispatcher
from jobpilot_agent.skills.registry import registry

router = APIRouter(tags=["Skills Debug"])


# ── Response Models ──────────────────────────────────────────────────────────


class SkillInfo(BaseModel):
    name: str
    version: str
    description: str
    when_to_use: str
    when_not_to_use: str
    tags: list[str]
    dependencies: list[str]


class SkillListResponse(BaseModel):
    count: int
    skills: list[SkillInfo]


class DispatchCheckRequest(BaseModel):
    """dispatch-check 端点的请求体，携带足够的 JDContext 字段用于路由判断。"""

    jd_text: str = "示例 JD 文本"
    user_id: str = "debug_user"
    request_id: str = "debug_req"
    user_context: UserContext = UserContext()
    classification: Optional[JDClassification] = None


class DispatchCheckResponse(BaseModel):
    skill_name: str
    should_invoke: bool
    reason: Optional[str] = None


class InvokeRequest(BaseModel):
    """invoke 端点的请求体。"""

    jd_text: str
    user_id: str = "debug_user"
    request_id: str = "debug_req"
    user_context: UserContext = UserContext()
    classification: Optional[JDClassification] = None
    timeout_seconds: int = 15


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=SkillListResponse,
    summary="列出所有已注册 Skill",
    description="返回当前进程中所有已通过 register_all_skills() 注册的 Skill 元信息。",
)
async def list_skills() -> SkillListResponse:
    """列出所有已注册的 Skill 及其元信息。"""
    skills = [
        SkillInfo(
            name=s.metadata.name,  # type: ignore[union-attr]
            version=s.metadata.version,  # type: ignore[union-attr]
            description=s.metadata.description,  # type: ignore[union-attr]
            when_to_use=s.metadata.when_to_use,  # type: ignore[union-attr]
            when_not_to_use=s.metadata.when_not_to_use,  # type: ignore[union-attr]
            tags=s.metadata.tags,  # type: ignore[union-attr]
            dependencies=s.metadata.dependencies,  # type: ignore[union-attr]
        )
        for s in registry.all()
    ]
    return SkillListResponse(count=len(skills), skills=skills)


@router.post(
    "/{name}/dispatch-check",
    response_model=DispatchCheckResponse,
    summary="检查指定 Skill 是否会被触发",
    description=(
        "给定 JDContext 片段，调用指定 Skill 的 should_invoke() 并返回结果。"
        "用于验证路由规则是否符合预期，不会真正执行 Skill。"
    ),
)
async def dispatch_check(
    name: str,
    body: DispatchCheckRequest,
) -> DispatchCheckResponse:
    """检查指定 Skill 在给定 context 下是否应触发。"""
    skill = registry.get(name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 未注册")

    ctx = JDContext(
        request_id=body.request_id,
        user_id=body.user_id,
        jd_text=body.jd_text,
        user_context=body.user_context,
        classification=body.classification,
    )

    try:
        result = skill.should_invoke(ctx)  # type: ignore[union-attr]
        return DispatchCheckResponse(skill_name=name, should_invoke=result)
    except Exception as exc:  # noqa: BLE001
        return DispatchCheckResponse(
            skill_name=name,
            should_invoke=False,
            reason=f"should_invoke 异常：{exc}",
        )


@router.post(
    "/{name}/invoke",
    summary="直接调用指定 Skill",
    description=(
        "直接触发某个 Skill 执行，绕过 LangGraph 流程。"
        "用于人工调试和验收测试，返回 SkillOutput 原始 JSON。"
    ),
    response_model=None,
)
async def invoke_skill(name: str, body: InvokeRequest) -> dict[str, Any]:
    """直接调用指定 Skill 并返回 SkillOutput。"""
    skill = registry.get(name)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' 未注册")

    ctx = JDContext(
        request_id=body.request_id,
        user_id=body.user_id,
        jd_text=body.jd_text,
        user_context=body.user_context,
        classification=body.classification,
        timeout_seconds=body.timeout_seconds,
    )

    output = await skill.invoke(ctx)  # type: ignore[union-attr]
    return output.model_dump()
