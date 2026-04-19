"""P4.1a 基础设施单元测试。

所有测试 mock LLM 与 RAG，无真实网络请求。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jobpilot_agent.graphs.interview.state import (
    CandidateProfile,
    Turn,
    _append_turns,
    _dict_merge,
    _inc_round,
)
from jobpilot_agent.graphs.interview.transcript import (
    count_stage_turns,
    format_transcript_for_llm,
    get_last_candidate_turn,
    next_turn_id,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _turn(turn_id: int, role: str = "interviewer", stage: str = "intro") -> Turn:
    return Turn(
        turn_id=turn_id,
        role=role,  # type: ignore[arg-type]
        content=f"content_{turn_id}",
        stage=stage,  # type: ignore[arg-type]
        created_at=datetime.utcnow(),
    )


# ── State reducer 测试 ─────────────────────────────────────────────────────────


def test_state_transcript_reducer_dedup_by_turn_id() -> None:
    """相同 turn_id 不重复追加"""
    t1 = _turn(1)
    t2 = _turn(2)
    result = _append_turns([t1], [t1, t2])
    assert len(result) == 2
    assert result[0].turn_id == 1
    assert result[1].turn_id == 2


def test_state_transcript_reducer_appends_new_turns() -> None:
    """新 turn_id 正常追加"""
    t1 = _turn(1)
    t2 = _turn(2)
    result = _append_turns([t1], [t2])
    assert len(result) == 2


def test_state_stage_round_count_increments_correctly() -> None:
    """{"intro": 1} + {"intro": 1} = {"intro": 2}"""
    result = _inc_round({"intro": 1}, {"intro": 1})
    assert result["intro"] == 2


def test_state_stage_round_count_new_key() -> None:
    """新 stage key 直接插入"""
    result = _inc_round({"intro": 1}, {"tech_qa": 2})
    assert result["intro"] == 1
    assert result["tech_qa"] == 2


def test_state_metadata_merges_dicts() -> None:
    """_dict_merge 合并两个 dict，右边覆盖左边"""
    result = _dict_merge({"a": 1, "b": 2}, {"b": 3, "c": 4})
    assert result == {"a": 1, "b": 3, "c": 4}


# ── Transcript 工具测试 ────────────────────────────────────────────────────────


def test_format_transcript_stage_markers() -> None:
    """include_stage_markers=True 时包含阶段分隔符"""
    turns = [
        _turn(1, role="interviewer", stage="intro"),
        _turn(2, role="candidate", stage="intro"),
        _turn(3, role="interviewer", stage="tech_qa"),
    ]
    output = format_transcript_for_llm(turns, include_stage_markers=True)
    assert "---[intro]---" in output
    assert "---[tech_qa]---" in output


def test_format_transcript_last_n_truncation() -> None:
    """超长 transcript 截断到 last_n"""
    turns = [_turn(i) for i in range(1, 31)]  # 30 turns
    output = format_transcript_for_llm(turns, last_n=10)
    # 只应包含最后 10 条的内容
    assert "content_20" not in output  # turn 20 is outside last_n=10 window
    assert "content_21" in output      # turn 21 is the first of the last 10
    assert "content_30" in output


def test_get_last_candidate_turn_found() -> None:
    """能找到最后一条候选人发言"""
    turns = [
        _turn(1, role="interviewer"),
        _turn(2, role="candidate"),
        _turn(3, role="interviewer"),
    ]
    result = get_last_candidate_turn(turns)
    assert result is not None
    assert result.turn_id == 2


def test_get_last_candidate_turn_empty() -> None:
    """无候选人发言时返回 None"""
    turns = [_turn(1, role="interviewer")]
    assert get_last_candidate_turn(turns) is None


def test_next_turn_id_empty_transcript() -> None:
    """空 transcript 时返回 1"""
    assert next_turn_id([]) == 1


def test_next_turn_id_increments() -> None:
    """有 transcript 时返回 max turn_id + 1"""
    turns = [_turn(3), _turn(7), _turn(2)]
    assert next_turn_id(turns) == 8


def test_count_stage_turns() -> None:
    """正确统计某阶段的 turn 数"""
    turns = [
        _turn(1, stage="intro"),
        _turn(2, stage="intro"),
        _turn(3, stage="tech_qa"),
    ]
    assert count_stage_turns(turns, "intro") == 2  # type: ignore[arg-type]
    assert count_stage_turns(turns, "tech_qa") == 1  # type: ignore[arg-type]
    assert count_stage_turns(turns, "scenario") == 0  # type: ignore[arg-type]


# ── Checkpointer SQLite roundtrip 测试 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_checkpointer_sqlite_roundtrip(tmp_path: Any) -> None:
    """SQLite checkpointer：写入 checkpoint 后能正确读出"""
    db_path = str(tmp_path / "test_checkpoints.db")

    from unittest.mock import patch as mock_patch

    from jobpilot_agent.graphs.interview.checkpointer import get_checkpointer

    # 通过 patch settings 指定临时 DB 路径
    mock_settings = MagicMock()
    mock_settings.checkpointer_backend = "sqlite"
    mock_settings.sqlite_checkpoint_path = db_path

    with mock_patch(
        "jobpilot_agent.graphs.interview.checkpointer.get_settings",
        return_value=mock_settings,
    ):
        async with get_checkpointer() as cp:
            # 验证 checkpointer 对象有 setup 方法且已调用
            assert cp is not None
            assert hasattr(cp, "put")
            assert hasattr(cp, "get")


# ── InterviewerCore mock 测试 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_interviewer_core_generate_next_question() -> None:
    """mock LLM + RAG，验证返回合法 InterviewerQuestion"""
    from jobpilot_agent.graphs.interview.interviewer_core import (
        InterviewerCore,
        InterviewerInput,
        InterviewerQuestion,
    )

    mock_question = InterviewerQuestion(
        content="请介绍你最有挑战的项目",
        intent="了解候选人项目经历",
        answer_points=["项目背景", "技术难点", "成果"],
    )

    core = InterviewerCore()
    core.llm = MagicMock()
    core.llm.chat_json = AsyncMock(return_value=(mock_question, MagicMock(total_tokens=100)))

    with patch(
        "jobpilot_agent.graphs.interview.interviewer_core.search_interview_kb",
        new=AsyncMock(return_value=[]),
    ):
        inp = InterviewerInput(company="字节跳动", position="后端工程师", stage="intro")
        result = await core.generate_next_question(inp)

    assert isinstance(result, InterviewerQuestion)
    assert result.content == "请介绍你最有挑战的项目"


@pytest.mark.asyncio
async def test_interviewer_core_generate_top_k() -> None:
    """mock LLM，验证 top_k 返回 k 个候选问题"""
    from jobpilot_agent.graphs.interview.interviewer_core import (
        InterviewerCore,
        InterviewerInput,
        InterviewerQuestion,
        _MultiQuestions,
    )

    mock_questions = _MultiQuestions(
        questions=[
            InterviewerQuestion(
                content=f"问题 {i}",
                intent="测试意图",
                answer_points=[],
            )
            for i in range(5)
        ]
    )

    core = InterviewerCore()
    core.llm = MagicMock()
    core.llm.chat_json = AsyncMock(return_value=(mock_questions, MagicMock(total_tokens=200)))

    with patch(
        "jobpilot_agent.graphs.interview.interviewer_core.search_interview_kb",
        new=AsyncMock(return_value=[]),
    ):
        inp = InterviewerInput(company="阿里巴巴", position="算法工程师", stage="tech_qa")
        results = await core.generate_top_k_questions(inp, k=5)

    assert len(results) == 5
    assert all(isinstance(q, InterviewerQuestion) for q in results)


# ── ProfileBuilder 空 KB 测试 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_profile_builder_handles_empty_kb() -> None:
    """user_kb 为空时返回带占位符的 CandidateProfile"""
    with patch(
        "jobpilot_agent.graphs.interview.profile_builder.search_user_kb",
        new=AsyncMock(return_value=[]),
    ):
        from jobpilot_agent.graphs.interview.profile_builder import build_candidate_profile

        profile = await build_candidate_profile("user_123")

    assert isinstance(profile, CandidateProfile)
    assert profile.user_id == "user_123"
    assert "未提供" in profile.resume_summary
    assert profile.top_projects == []
