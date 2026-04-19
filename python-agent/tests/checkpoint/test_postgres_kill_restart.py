"""PostgreSQL checkpointer kill-restart 一致性测试。

与 SQLite 版测试结构完全一致，区别仅在使用 postgres backend。
若未设置 POSTGRES_TEST_URL 则自动跳过。

运行前提：
  export POSTGRES_TEST_URL="postgresql://postgres:pass@localhost:5432/test_checkpoint"
  uv run pytest tests/checkpoint/test_postgres_kill_restart.py -v -m checkpoint
"""

from __future__ import annotations

import os
import uuid

import pytest

from tests.checkpoint.helpers.mock_client import InterviewMockClient, run_n_rounds
from tests.checkpoint.helpers.process_manager import agent_process
from tests.checkpoint.helpers.state_comparator import assert_states_equal, summarize_state

pytestmark = [pytest.mark.integration, pytest.mark.checkpoint]

_SKIP = pytest.mark.skipif(
    not os.getenv("POSTGRES_TEST_URL"),
    reason="POSTGRES_TEST_URL not set — skip Postgres checkpoint tests",
)
_PORT = 18002  # 与 SQLite 测试端口错开，防止并发冲突


@_SKIP
@pytest.mark.asyncio
async def test_pg_kill_at_round_5_restart_continues(postgres_url: str | None) -> None:
    """核心测试（Postgres）：5 轮 → kill → 重启 → 状态一致 → 跑完。"""
    assert postgres_url is not None
    thread_id = f"test_pg_kr_{uuid.uuid4().hex[:8]}"

    async with agent_process("postgres", port=_PORT) as proc1:
        c1 = InterviewMockClient(proc1.base_url, thread_id)
        start_data = await c1.start("字节跳动", "高级后端工程师")
        assert start_data["state"] == "waiting_user_input"

        await run_n_rounds(c1, start_data, n_rounds=5)
        state_before = await c1.get_full_state()
        await c1.close()
        print(f"\n[BEFORE KILL] {summarize_state(state_before)}")
        proc1.kill_hard()

    async with agent_process("postgres", port=_PORT) as proc2:
        c2 = InterviewMockClient(proc2.base_url, thread_id)
        state_after = await c2.get_full_state()
        print(f"[AFTER RESTART] {summarize_state(state_after)}")

        assert_states_equal(state_before, state_after)

        status = await c2.status()
        assert status["state"] == "waiting_user_input"

        resume_entry = {
            "state": "waiting_user_input",
            "next_action": {
                "content": "（断点恢复）",
                "stage": state_after["values"]["current_stage"],  # type: ignore[index]
            },
        }
        final = await run_n_rounds(c2, resume_entry, n_rounds=30)
        assert final["state"] == "completed"
        assert "report" in final

        await c2.close()


@_SKIP
@pytest.mark.asyncio
async def test_pg_kill_multiple_times(postgres_url: str | None) -> None:
    """变态场景（Postgres）：多次 kill + restart。"""
    assert postgres_url is not None
    thread_id = f"test_pg_multi_{uuid.uuid4().hex[:8]}"

    async with agent_process("postgres", port=_PORT) as p:
        c = InterviewMockClient(p.base_url, thread_id)
        start_data = await c.start("腾讯", "Java 后端")
        await run_n_rounds(c, start_data, n_rounds=3)
        state1 = await c.get_full_state()
        await c.close()
        p.kill_hard()

    async with agent_process("postgres", port=_PORT) as p:
        c = InterviewMockClient(p.base_url, thread_id)
        state1_after = await c.get_full_state()
        assert_states_equal(state1, state1_after)

        resume_entry = {
            "state": "waiting_user_input",
            "next_action": {"stage": state1_after["values"]["current_stage"]},  # type: ignore[index]
        }
        await run_n_rounds(c, resume_entry, n_rounds=4)
        state2 = await c.get_full_state()
        await c.close()
        p.kill_hard()

    async with agent_process("postgres", port=_PORT) as p:
        c = InterviewMockClient(p.base_url, thread_id)
        state2_after = await c.get_full_state()
        assert_states_equal(state2, state2_after)

        resume_entry = {
            "state": "waiting_user_input",
            "next_action": {"stage": state2_after["values"]["current_stage"]},  # type: ignore[index]
        }
        final = await run_n_rounds(c, resume_entry, n_rounds=30)
        assert final["state"] == "completed"
        await c.close()


@_SKIP
@pytest.mark.asyncio
async def test_pg_kill_during_interrupt_preserves_last_question(
    postgres_url: str | None,
) -> None:
    """interrupt 期间 kill——面试官问题不丢失（Postgres）。"""
    assert postgres_url is not None
    thread_id = f"test_pg_interrupt_{uuid.uuid4().hex[:8]}"

    async with agent_process("postgres", port=_PORT) as p:
        c = InterviewMockClient(p.base_url, thread_id)
        start_data = await c.start("美团", "数据工程师")
        state_data = await run_n_rounds(c, start_data, n_rounds=4)
        assert state_data["state"] == "waiting_user_input"
        last_question = state_data["next_action"]["content"]  # type: ignore[index]

        state_before = await c.get_full_state()
        await c.close()
        p.kill_hard()

    async with agent_process("postgres", port=_PORT) as p:
        c = InterviewMockClient(p.base_url, thread_id)
        state_after = await c.get_full_state()
        assert_states_equal(state_before, state_after)

        transcript = state_after["values"]["transcript"]  # type: ignore[index]
        interviewer_turns = [t for t in transcript if t["role"] == "interviewer"]  # type: ignore[index]
        assert interviewer_turns[-1]["content"] == last_question

        await c.close()


@_SKIP
@pytest.mark.asyncio
async def test_pg_concurrent_threads_dont_interfere(postgres_url: str | None) -> None:
    """并发多 thread kill 后互不干扰（Postgres）。"""
    assert postgres_url is not None
    thread_a = f"test_pg_a_{uuid.uuid4().hex[:8]}"
    thread_b = f"test_pg_b_{uuid.uuid4().hex[:8]}"

    async with agent_process("postgres", port=_PORT) as p:
        ca = InterviewMockClient(p.base_url, thread_a)
        cb = InterviewMockClient(p.base_url, thread_b)

        start_a = await ca.start("滴滴", "前端")
        start_b = await cb.start("京东", "算法")

        await run_n_rounds(ca, start_a, n_rounds=3)
        await run_n_rounds(cb, start_b, n_rounds=3)

        state_a_before = await ca.get_full_state()
        state_b_before = await cb.get_full_state()
        await ca.close()
        await cb.close()
        p.kill_hard()

    async with agent_process("postgres", port=_PORT) as p:
        ca = InterviewMockClient(p.base_url, thread_a)
        cb = InterviewMockClient(p.base_url, thread_b)

        assert_states_equal(state_a_before, await ca.get_full_state())
        assert_states_equal(state_b_before, await cb.get_full_state())

        await ca.close()
        await cb.close()
