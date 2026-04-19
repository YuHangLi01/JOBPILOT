"""scenario 节点 + judge 条件边函数。"""

from __future__ import annotations

from jobpilot_agent.graphs.interview.interviewer_core import InterviewerInput, get_interviewer_core
from jobpilot_agent.graphs.interview.nodes.base import run_interview_turn
from jobpilot_agent.graphs.interview.state import CandidateProfile, InterviewState
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

_MAX_ROUNDS = 3
_MIN_ROUNDS = 1


async def scenario_node(state: InterviewState) -> dict[str, object]:
    """情境题：每次执行出 1 问 + 等答 + 打分，循环由条件边驱动。"""
    return await run_interview_turn(state, stage="scenario", max_stage_rounds=_MAX_ROUNDS)


async def judge_continue_scenario(state: InterviewState) -> str:
    """条件边函数：决定是继续情境题还是推进到 reverse。

    Returns:
        "continue"：继续当前阶段
        "move_to_reverse"：推进下一阶段
    """
    rounds = (state.get("stage_round_count") or {}).get("scenario", 0)

    if rounds >= _MAX_ROUNDS:
        log.info("judge_scenario.hard_stop", rounds=rounds)
        return "move_to_reverse"

    if rounds < _MIN_ROUNDS:
        return "continue"

    profile_raw = state.get("candidate_profile")
    profile = CandidateProfile.model_validate(profile_raw) if profile_raw else None

    core = get_interviewer_core()
    should_continue = await core.judge_should_continue(
        InterviewerInput(
            company=str(state.get("company", "")),
            position=str(state.get("position", "")),
            stage="scenario",
            candidate_profile=profile,
            transcript=list(state.get("transcript") or []),
            stage_round=rounds,
            max_stage_rounds=_MAX_ROUNDS,
        )
    )
    log.info("judge_scenario.llm", rounds=rounds, continue_=should_continue)
    return "continue" if should_continue else "move_to_reverse"
