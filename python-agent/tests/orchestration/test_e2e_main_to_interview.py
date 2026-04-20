"""端到端集成测试：JD 路由 → session_context → 面试启动。

标记为 integration — 需要真实 Redis、LLM 服务。
运行：cd python-agent && uv run pytest tests/orchestration/test_e2e_main_to_interview.py -m integration
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration]

# ── 辅助 JD 文本 ──────────────────────────────────────────────────────────────

_BYTEDANCE_FRONTEND_JD = """
职位：高级前端工程师
公司：字节跳动
地点：北京

岗位职责：
- 负责抖音 Web 端核心功能研发
- 参与前端架构设计与技术选型
- 与产品、设计协同推进业务快速迭代

任职要求：
- 3 年以上前端开发经验
- 精通 React / TypeScript / Webpack 工具链
- 深入理解浏览器渲染机制与性能优化
- 有大型 SPA 项目架构经验者优先
"""

_MGMT_JD = """
职位：首席执行官（CEO）
公司：某初创公司
地点：上海

岗位职责：
- 制定公司战略方向
- 管理高管团队，推动公司整体目标落地

任职要求：
- 10 年以上管理经验
- 有成功 IPO 或融资经历者优先
"""


# ── 辅助函数 ──────────────────────────────────────────────────────────────────


async def _run_routing(client: AsyncClient, chat_id: str, jd_text: str = _BYTEDANCE_FRONTEND_JD) -> dict:
    r = await client.post(
        "/api/v1/agent/jd-routing",
        json={
            "request_id": str(uuid.uuid4()),
            "user_id": "test_user",
            "jd_text": jd_text,
            "user_context": {
                "feishu_chat_id": chat_id,
                "preferred_lang": "zh",
            },
        },
        timeout=120,
    )
    assert r.status_code == 200, r.text
    return r.json()


# ── 测试场景 ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jd_routing_produces_invitation(app_client: AsyncClient):
    """JD 路由跑完后应在 results 里携带 interview_invitation 字段。"""
    chat_id = f"test_inv_{uuid.uuid4().hex[:8]}"
    data = await _run_routing(app_client, chat_id)

    results = data.get("results", {})
    # 如果面经库无数据，invitation 可能为 None；仅断言字段存在
    assert "interview_invitation" in results


@pytest.mark.asyncio
async def test_mgmt_jd_does_not_invite_interview(app_client: AsyncClient):
    """mgmt 岗位不应产生 interview_invitation（或 should_invite=False）。"""
    chat_id = f"test_mgmt_{uuid.uuid4().hex[:8]}"
    data = await _run_routing(app_client, chat_id, jd_text=_MGMT_JD)

    invitation = data["results"].get("interview_invitation")
    assert invitation is None or invitation["should_invite"] is False


@pytest.mark.asyncio
async def test_interview_start_resolves_company_from_session_context(app_client: AsyncClient):
    """先跑 JD 路由写入 session_context，再启动面试时不传 company/position，应能自动补齐。"""
    chat_id = f"test_ctx_{uuid.uuid4().hex[:8]}"
    routing_data = await _run_routing(app_client, chat_id)

    invitation = routing_data["results"].get("interview_invitation")
    if not invitation or not invitation.get("should_invite"):
        pytest.skip("interview_rag coverage too low or mgmt JD — skip interview start test")

    # 不传 company/position，验证 session_context 自动注入
    r = await app_client.post(
        "/api/v1/agent/interview/start",
        json={
            "thread_id": chat_id,
            "user_id": "test_user",
        },
        timeout=60,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["state"] in ("waiting_user_input", "completed")


@pytest.mark.asyncio
async def test_interview_start_400_without_context_or_params(app_client: AsyncClient):
    """既没有 session_context 也没有传 company/position 时，应返回 400。"""
    thread_id = f"fresh_{uuid.uuid4().hex[:8]}"

    r = await app_client.post(
        "/api/v1/agent/interview/start",
        json={
            "thread_id": thread_id,
            "user_id": "test_user",
            # 故意不传 company/position，且无 session_context
        },
        timeout=30,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_session_context_ttl_and_cleanup(app_client: AsyncClient):
    """session_context save / load / clear 生命周期测试。"""
    from jobpilot_agent.orchestration.session_context import get_session_store

    chat_id = f"test_ttl_{uuid.uuid4().hex[:8]}"
    await _run_routing(app_client, chat_id)

    store = get_session_store()
    ctx = await store.load(chat_id)
    # 若 invitation 未产生（面经库无数据），context 不会存入 Redis
    if ctx is None:
        pytest.skip("No session_context saved (interview_rag coverage too low)")

    assert "jd_summary" in ctx
    assert "interview_invitation" in ctx

    await store.clear(chat_id)
    assert await store.load(chat_id) is None
