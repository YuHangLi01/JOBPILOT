"""端到端集成测试：完整面试流程 happy path。

标记为 @pytest.mark.integration，依赖真实 LLM + SQLite checkpointer。

运行：
    UV_PROJECT_ENVIRONMENT=/tmp/jobpilot-venv uv run pytest -m integration \
        tests/graphs/interview/test_e2e_happy_path.py -v
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def app_client():
    """使用 ASGI transport 直接调 FastAPI，无需真实 HTTP 端口。"""
    from jobpilot_agent.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ── 辅助函数 ──────────────────────────────────────────────────────────────────


def _generate_mock_answer(next_action: dict) -> str:
    """根据阶段生成模拟答案（避免空回答触发 LLM 降级）。"""
    stage = next_action.get("stage", "intro")
    answers = {
        "intro": "我是一名有 5 年经验的后端工程师，熟悉 Python 和分布式系统，主导过多个高并发项目。",
        "project_deep_dive": (
            "我在上一家公司主导了一个电商平台的订单系统重构，"
            "将 TPS 从 1000 提升到 10000，使用了分库分表 + Redis 缓存 + 消息队列方案。"
        ),
        "tech_qa": (
            "Redis 集群使用 Gossip 协议做节点发现，一致性哈希分槽。"
            "分布式锁用 RedLock 算法，需要多数节点获取锁才算成功。"
        ),
        "scenario": (
            "遇到这种情况我会先做限流降级，保护核心链路，"
            "同时触发告警让 oncall 介入，然后回滚有问题的变更。"
        ),
        "reverse": "请问贵公司的技术团队规模如何？工程师的晋升通道是怎样的？",
        "closing": "好的，谢谢面试官，期待后续消息。",
    }
    return answers.get(stage, "我理解这个问题，以下是我的回答：这是一个很好的问题，需要从多个角度分析。")


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_e2e_full_interview(app_client: AsyncClient) -> None:
    """完整跑一次面试：start → 多次 resume → completed，验证 report 结构。"""
    thread_id = "test_thread_e2e_full"

    # 1. 启动
    resp = await app_client.post(
        "/api/v1/agent/interview/start",
        json={
            "thread_id": thread_id,
            "user_id": "test_user",
            "company": "字节跳动",
            "position": "高级后端工程师",
            "context": {},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "waiting_user_input"
    assert data["next_action"]["stage"] == "intro"
    assert data["next_action"]["content"]  # 非空问题

    # 2. 连续 resume
    max_rounds = 30
    for _ in range(max_rounds):
        user_answer = _generate_mock_answer(data["next_action"])
        resp = await app_client.post(
            "/api/v1/agent/interview/resume",
            json={"thread_id": thread_id, "user_input": user_answer},
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["state"] == "completed":
            break
    else:
        pytest.fail(f"Interview did not complete within {max_rounds} rounds")

    # 3. 校验报告
    assert "report" in data
    report = data["report"]
    assert "stage_scores" in report
    assert isinstance(report["stage_scores"], list)
    assert len(report["stage_scores"]) > 0
    assert "highlights" in report
    assert "improvements" in report
    assert "transcript_summary" in report

    # 4. 验证 status
    resp = await app_client.get(f"/api/v1/agent/interview/{thread_id}/status")
    assert resp.status_code == 200
    status = resp.json()
    assert status["state"] == "completed"
    assert status["transcript_length"] > 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_status_for_unknown_thread(app_client: AsyncClient) -> None:
    """查询不存在的 thread 应返回 not_found（200 OK）。"""
    resp = await app_client.get("/api/v1/agent/interview/nonexistent_thread_xyz/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "not_found"
