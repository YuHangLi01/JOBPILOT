"""project_deep_dive 节点 + judge 条件边函数。"""

from __future__ import annotations

from jobpilot_agent.graphs.interview.interviewer_core import InterviewerInput, get_interviewer_core
from jobpilot_agent.graphs.interview.nodes.base import run_interview_turn
from jobpilot_agent.graphs.interview.state import CandidateProfile, InterviewState
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

_MAX_ROUNDS = 5
_MIN_ROUNDS = 2


async def project_deep_dive_node(state: InterviewState) -> dict[str, object]:
    """项目深挖：每次执行出 1 问 + 等答 + 打分，循环由条件边驱动。"""
    return await run_interview_turn(state, stage="project_deep_dive", max_stage_rounds=_MAX_ROUNDS)


async def judge_continue_deep_dive(state: InterviewState) -> str:
    """条件边函数：决定是继续深挖还是推进到 tech_qa。

    Returns:
        "continue"：继续当前阶段
        "move_to_tech_qa"：推进下一阶段
    """
    rounds = (state.get("stage_round_count") or {}).get("project_deep_dive", 0)

    if rounds >= _MAX_ROUNDS:
        log.info("judge_deep_dive.hard_stop", rounds=rounds)
        return "move_to_tech_qa"

    if rounds < _MIN_ROUNDS:
        return "continue"

    # 软门限：LLM 判断
    profile_raw = state.get("candidate_profile")
    profile = CandidateProfile.model_validate(profile_raw) if profile_raw else None

    core = get_interviewer_core()
    should_continue = await core.judge_should_continue(
        InterviewerInput(
            company=str(state.get("company", "")),
            position=str(state.get("position", "")),
            stage="project_deep_dive",
            candidate_profile=profile,
            transcript=list(state.get("transcript") or []),
            stage_round=rounds,
            max_stage_rounds=_MAX_ROUNDS,
        )
    )
    log.info("judge_deep_dive.llm", rounds=rounds, continue_=should_continue)
    return "continue" if should_continue else "move_to_tech_qa"
