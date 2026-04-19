"""intro 节点：开场自我介绍引导（1 轮，不循环）。"""

from __future__ import annotations

from jobpilot_agent.graphs.interview.nodes.base import run_interview_turn
from jobpilot_agent.graphs.interview.state import InterviewState


async def intro_node(state: InterviewState) -> dict[str, object]:
    """自我介绍环节：面试官出 1 问，等候选人答，打分后推进到 project_deep_dive。"""
    updates = await run_interview_turn(state, stage="intro", max_stage_rounds=1)
    return {
        **updates,
        "current_stage": "project_deep_dive",
        "stage_history": ["intro"],
    }
