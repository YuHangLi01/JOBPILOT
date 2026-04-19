"""P4.1b 节点单元测试。

Mock 策略：
- get_interviewer_core() → MagicMock，避免真实 LLM/RAG 调用
- get_llm_client() → MagicMock，用于 reverse/closing/evaluate 直接调用 LLM
- ask_user_interrupt → 直接返回字符串（不触发 LangGraph interrupt）
- build_candidate_profile → 返回固定 CandidateProfile
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jobpilot_agent.graphs.interview.interviewer_core import InterviewerQuestion
from jobpilot_agent.graphs.interview.state import (
    CandidateProfile,
    InterviewReport,
    InterviewState,
    PerformanceSignal,
)

# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _make_state(**kwargs: object) -> InterviewState:
    defaults: InterviewState = {
        "session_id": "sess-1",
        "user_id": "user-1",
        "company": "测试科技",
        "position": "后端工程师",
        "transcript": [],
        "stage_round_count": {},
        "performance_signals": [],
        "stage_history": [],
        "errors": [],
        "metadata": {},
        "candidate_profile": {
            "user_id": "user-1",
            "resume_summary": "5年后端经验",
            "top_projects": ["电商平台"],
            "tech_strengths": ["Python", "Redis"],
            "potential_weaknesses": ["分布式系统"],
        },
    }
    defaults.update(kwargs)  # type: ignore[typeddict-item]
    return defaults


def _mock_question() -> InterviewerQuestion:
    return InterviewerQuestion(
        content="请介绍你最有挑战的项目",
        intent="了解项目经验",
        answer_points=["项目规模", "技术难点", "个人贡献"],
    )


def _mock_signals(turn_id: int = 1, stage: str = "intro") -> list[PerformanceSignal]:
    return [
        PerformanceSignal(
            turn_id=turn_id,
            stage=stage,  # type: ignore[arg-type]
            dimension="clarity",
            score=8.0,
            evidence="表达清晰",
        )
    ]


# ── init_session_node ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_init_session_builds_profile() -> None:
    mock_profile = CandidateProfile(
        user_id="user-1",
        resume_summary="5年后端经验",
        top_projects=["电商平台"],
        tech_strengths=["Python"],
        potential_weaknesses=["分布式"],
    )
    state: InterviewState = {
        "session_id": "s1",
        "user_id": "user-1",
        "company": "测试科技",
        "position": "后端工程师",
        "transcript": [],
        "stage_round_count": {},
        "performance_signals": [],
        "stage_history": [],
        "errors": [],
        "metadata": {},
    }

    with patch(
        "jobpilot_agent.graphs.interview.nodes.init.build_candidate_profile",
        new_callable=AsyncMock,
        return_value=mock_profile,
    ):
        from jobpilot_agent.graphs.interview.nodes.init import init_session_node

        result = await init_session_node(state)

    assert result["current_stage"] == "intro"
    assert result["transcript"] == []
    assert result["stage_round_count"] == {}
    assert isinstance(result["candidate_profile"], dict)
    assert result["candidate_profile"]["user_id"] == "user-1"  # type: ignore[index]


# ── intro_node ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_intro_node_appends_two_turns() -> None:
    state = _make_state()
    mock_core = MagicMock()
    mock_core.generate_next_question = AsyncMock(return_value=_mock_question())
    mock_core.evaluate_candidate_answer = AsyncMock(return_value=_mock_signals(turn_id=1, stage="intro"))

    with (
        patch("jobpilot_agent.graphs.interview.nodes.base.get_interviewer_core", return_value=mock_core),
        patch(
            "jobpilot_agent.graphs.interview.nodes.base.ask_user_interrupt",
            return_value="我做过一个高并发电商系统",
        ),
    ):
        from jobpilot_agent.graphs.interview.nodes.intro import intro_node

        result = await intro_node(state)

    turns = result["transcript"]
    assert isinstance(turns, list)
    assert len(turns) == 2
    assert turns[0].role == "interviewer"  # type: ignore[union-attr]
    assert turns[1].role == "candidate"  # type: ignore[union-attr]
    assert result["current_stage"] == "project_deep_dive"
    assert "intro" in result["stage_history"]


# ── project_deep_dive_node ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_project_deep_dive_round_count_increments() -> None:
    state = _make_state()
    mock_core = MagicMock()
    mock_core.generate_next_question = AsyncMock(return_value=_mock_question())
    mock_core.evaluate_candidate_answer = AsyncMock(
        return_value=_mock_signals(turn_id=1, stage="project_deep_dive")
    )

    with (
        patch("jobpilot_agent.graphs.interview.nodes.base.get_interviewer_core", return_value=mock_core),
        patch(
            "jobpilot_agent.graphs.interview.nodes.base.ask_user_interrupt",
            return_value="项目中我负责架构设计",
        ),
    ):
        from jobpilot_agent.graphs.interview.nodes.project_deep_dive import project_deep_dive_node

        result = await project_deep_dive_node(state)

    assert result["stage_round_count"] == {"project_deep_dive": 1}


# ── judge_continue_deep_dive ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_judge_deep_dive_stops_at_5_rounds() -> None:
    state = _make_state(stage_round_count={"project_deep_dive": 5})

    from jobpilot_agent.graphs.interview.nodes.project_deep_dive import judge_continue_deep_dive

    # 硬停，不应调用 LLM
    with patch("jobpilot_agent.graphs.interview.nodes.project_deep_dive.get_interviewer_core") as mock:
        result = await judge_continue_deep_dive(state)
        mock.assert_not_called()

    assert result == "move_to_tech_qa"


@pytest.mark.asyncio
async def test_judge_deep_dive_continues_at_1_round() -> None:
    state = _make_state(stage_round_count={"project_deep_dive": 1})

    from jobpilot_agent.graphs.interview.nodes.project_deep_dive import judge_continue_deep_dive

    with patch("jobpilot_agent.graphs.interview.nodes.project_deep_dive.get_interviewer_core") as mock:
        result = await judge_continue_deep_dive(state)
        mock.assert_not_called()

    assert result == "continue"


@pytest.mark.asyncio
async def test_judge_deep_dive_calls_llm_at_3_rounds() -> None:
    state = _make_state(stage_round_count={"project_deep_dive": 3})
    mock_core = MagicMock()
    mock_core.judge_should_continue = AsyncMock(return_value=True)

    from jobpilot_agent.graphs.interview.nodes.project_deep_dive import judge_continue_deep_dive

    with patch(
        "jobpilot_agent.graphs.interview.nodes.project_deep_dive.get_interviewer_core",
        return_value=mock_core,
    ):
        result = await judge_continue_deep_dive(state)

    mock_core.judge_should_continue.assert_awaited_once()
    assert result == "continue"


# ── reverse_node ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reverse_node_produces_3_turns() -> None:
    state = _make_state()
    from jobpilot_agent.graphs.interview.nodes.reverse import _ReverseAnswer, reverse_node

    mock_llm = MagicMock()
    mock_llm.chat_json = AsyncMock(return_value=(_ReverseAnswer(content="我们团队氛围很好"), MagicMock()))

    with (
        patch(
            "jobpilot_agent.graphs.interview.nodes.reverse.ask_user_interrupt",
            return_value="请问贵公司的技术栈是什么？",
        ),
        patch(
            "jobpilot_agent.graphs.interview.nodes.reverse.get_llm_client",
            return_value=mock_llm,
        ),
    ):
        result = await reverse_node(state)

    turns = result["transcript"]
    assert isinstance(turns, list)
    assert len(turns) == 3
    assert turns[0].role == "interviewer"  # invite
    assert turns[1].role == "candidate"  # candidate question
    assert turns[2].role == "interviewer"  # answer
    assert result["current_stage"] == "closing"


# ── evaluate_performance_node ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_evaluate_performance_valid_report() -> None:
    signals = _mock_signals(turn_id=1, stage="intro") + _mock_signals(turn_id=3, stage="tech_qa")
    state = _make_state(performance_signals=signals)

    mock_report = InterviewReport(
        stage_scores={"intro": 8.0, "tech_qa": 7.5},
        highlights=["表现优秀"],
        improvements=["深度不足"],
        transcript_summary="候选人整体表现良好",
    )
    mock_llm = MagicMock()
    mock_llm.chat_json = AsyncMock(return_value=(mock_report, MagicMock()))

    with patch(
        "jobpilot_agent.graphs.interview.nodes.evaluate.get_llm_client",
        return_value=mock_llm,
    ):
        from jobpilot_agent.graphs.interview.nodes.evaluate import evaluate_performance_node

        result = await evaluate_performance_node(state)

    assert "report" in result
    validated = InterviewReport.model_validate(result["report"])
    assert validated.transcript_summary == "候选人整体表现良好"


# ── run_interview_turn error fallback ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_interview_turn_error_fallback() -> None:
    """LLM 抛异常时应返回含 errors 的降级 dict，不向外传播异常。"""
    state = _make_state()
    mock_core = MagicMock()
    mock_core.generate_next_question = AsyncMock(side_effect=RuntimeError("LLM 超时"))

    with (
        patch("jobpilot_agent.graphs.interview.nodes.base.get_interviewer_core", return_value=mock_core),
        patch(
            "jobpilot_agent.graphs.interview.nodes.base.ask_user_interrupt",
            return_value="不应被调用",
        ),
    ):
        from jobpilot_agent.graphs.interview.nodes.base import run_interview_turn

        result = await run_interview_turn(state, stage="intro", max_stage_rounds=1)

    assert "errors" in result
    errors = result["errors"]
    assert isinstance(errors, list)
    assert len(errors) == 1
    assert "RuntimeError" in errors[0]["error"]  # type: ignore[index]
