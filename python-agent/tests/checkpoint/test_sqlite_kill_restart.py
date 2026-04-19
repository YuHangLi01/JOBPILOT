"""SQLite checkpointer kill-restart 一致性测试。

这些测试验证：进程被 SIGKILL 强制终止后，用同一个 SQLite 文件重启，
transcript / current_stage / performance_signals 等 6 个字段 100% 一致。
"""

from __future__ import annotations

import uuid

import pytest

from tests.checkpoint.helpers.mock_client import InterviewMockClient, run_n_rounds
from tests.checkpoint.helpers.process_manager import agent_process
from tests.checkpoint.helpers.state_comparator import assert_states_equal, summarize_state

pytestmark = [pytest.mark.integration, pytest.mark.checkpoint]

_PORT = 18001


@pytest.mark.asyncio
async def test_kill_at_round_5_restart_continues(sqlite_path: str) -> None:
    """核心测试：跑 5 轮 → SIGKILL → 重启 → 状态一致 → 继续跑完。"""
    thread_id = f"test_kr_{uuid.uuid4().hex[:8]}"

    # ===== Phase 1：启动、面试 5 轮、快照 =====
    async with agent_process("sqlite", sqlite_path, port=_PORT) as proc1:
        c1 = InterviewMockClient(proc1.base_url, thread_id)
        start_data = await c1.start(company="字节跳动", position="高级后端工程师")
        assert start_data["state"] == "waiting_user_input", f"Unexpected state: {start_data}"

        _ = await run_n_rounds(c1, start_data, n_rounds=5)

        state_before = await c1.get_full_state()
        await c1.close()
        print(f"\n[BEFORE KILL] {summarize_state(state_before)}")
        proc1.kill_hard()

    # ===== Phase 2：重启、对比状态 =====
    async with agent_process("sqlite", sqlite_path, port=_PORT) as proc2:
        c2 = InterviewMockClient(proc2.base_url, thread_id)

        state_after = await c2.get_full_state()
        print(f"[AFTER RESTART] {summarize_state(state_after)}")

        # 断言 1：严格状态一致
        assert_states_equal(state_before, state_after)

        # 断言 2：status 正常
        status = await c2.status()
        assert status["state"] == "waiting_user_input"
        assert status["current_stage"] is not None

        # 断言 3：从断点继续能跑完
        resume_entry = {
            "state": "waiting_user_input",
            "next_action": {
                "content": "（断点恢复）",
                "stage": state_after["values"]["current_stage"],  # type: ignore[index]
            },
        }
        final = await run_n_rounds(c2, resume_entry, n_rounds=30)
        assert final["state"] == "completed", f"Expected completed, got: {final['state']}"
        assert "report" in final
        assert "stage_scores" in final["report"]  # type: ignore[operator]

        await c2.close()


@pytest.mark.asyncio
async def test_kill_multiple_times(sqlite_path: str) -> None:
    """变态场景：面试过程中多次 kill + restart。"""
    thread_id = f"test_multi_kill_{uuid.uuid4().hex[:8]}"

    # 第 1 段：跑 3 轮
    async with agent_process("sqlite", sqlite_path, port=_PORT) as p:
        c = InterviewMockClient(p.base_url, thread_id)
        start_data = await c.start("阿里巴巴", "产品经理")
        await run_n_rounds(c, start_data, n_rounds=3)
        state1 = await c.get_full_state()
        await c.close()
        p.kill_hard()

    # 第 2 段：验证恢复，再跑 4 轮
    async with agent_process("sqlite", sqlite_path, port=_PORT) as p:
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

    # 第 3 段：验证恢复，跑完
    async with agent_process("sqlite", sqlite_path, port=_PORT) as p:
        c = InterviewMockClient(p.base_url, thread_id)
        state2_after = await c.get_full_state()
        assert_states_equal(state2, state2_after)

        # transcript 单调增加
        t1_count = len(state1["values"]["transcript"])  # type: ignore[index]
        t2_count = len(state2_after["values"]["transcript"])  # type: ignore[index]
        assert t2_count >= t1_count, "transcript must grow monotonically"

        resume_entry = {
            "state": "waiting_user_input",
            "next_action": {"stage": state2_after["values"]["current_stage"]},  # type: ignore[index]
        }
        final = await run_n_rounds(c, resume_entry, n_rounds=30)
        assert final["state"] == "completed"
        await c.close()


@pytest.mark.asyncio
async def test_kill_during_interrupt_preserves_last_question(sqlite_path: str) -> None:
    """在 Bot 提问后、用户回答前 kill——问题本身不丢失。"""
    thread_id = f"test_interrupt_kill_{uuid.uuid4().hex[:8]}"

    async with agent_process("sqlite", sqlite_path, port=_PORT) as p:
        c = InterviewMockClient(p.base_url, thread_id)
        start_data = await c.start("腾讯", "后端工程师")

        # 推进 4 轮，确保有多条 transcript
        state_data = await run_n_rounds(c, start_data, n_rounds=4)
        assert state_data["state"] == "waiting_user_input"
        last_question = state_data["next_action"]["content"]  # type: ignore[index]

        state_before = await c.get_full_state()
        await c.close()
        p.kill_hard()

    async with agent_process("sqlite", sqlite_path, port=_PORT) as p:
        c = InterviewMockClient(p.base_url, thread_id)
        state_after = await c.get_full_state()
        assert_states_equal(state_before, state_after)

        # 问题保存在 interrupt payload 里（kill 时 q_turn 尚未 commit 到 transcript）
        interrupts = state_after.get("interrupts") or []  # type: ignore[union-attr]
        assert len(interrupts) > 0, "interrupt payload should be preserved after kill+restart"
        assert interrupts[0]["value"]["content"] == last_question

        await c.close()


@pytest.mark.asyncio
async def test_concurrent_threads_dont_interfere(sqlite_path: str) -> None:
    """多个 thread_id 同时面试，kill 后各自独立恢复，互不干扰。"""
    thread_a = f"test_thread_a_{uuid.uuid4().hex[:8]}"
    thread_b = f"test_thread_b_{uuid.uuid4().hex[:8]}"

    async with agent_process("sqlite", sqlite_path, port=_PORT) as p:
        ca = InterviewMockClient(p.base_url, thread_a)
        cb = InterviewMockClient(p.base_url, thread_b)

        start_a = await ca.start("字节跳动", "前端工程师")
        start_b = await cb.start("阿里巴巴", "算法工程师")

        await run_n_rounds(ca, start_a, n_rounds=3)
        await run_n_rounds(cb, start_b, n_rounds=4)

        state_a_before = await ca.get_full_state()
        state_b_before = await cb.get_full_state()

        # 两个 session 的公司不同，隔离验证
        assert state_a_before["values"]["company"] != state_b_before["values"]["company"]  # type: ignore[index]

        await ca.close()
        await cb.close()
        p.kill_hard()

    async with agent_process("sqlite", sqlite_path, port=_PORT) as p:
        ca = InterviewMockClient(p.base_url, thread_a)
        cb = InterviewMockClient(p.base_url, thread_b)

        state_a_after = await ca.get_full_state()
        state_b_after = await cb.get_full_state()

        assert_states_equal(state_a_before, state_a_after)
        assert_states_equal(state_b_before, state_b_after)

        await ca.close()
        await cb.close()
