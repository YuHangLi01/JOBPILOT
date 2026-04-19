"""closing_node：面试结束语节点。"""

from __future__ import annotations

from pydantic import BaseModel

from jobpilot_agent.graphs.interview.prompts.evaluate import build_closing_prompt
from jobpilot_agent.graphs.interview.state import InterviewState, Turn
from jobpilot_agent.graphs.interview.transcript import next_turn_id
from jobpilot_agent.integrations.llm_client import get_llm_client
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


class _ClosingText(BaseModel):
    content: str


async def closing_node(state: InterviewState) -> dict[str, object]:
    """生成面试结束语，产生 1 条 system 类型 transcript。"""
    transcript: list[Turn] = list(state.get("transcript") or [])
    company = str(state.get("company", ""))
    position = str(state.get("position", ""))

    llm = get_llm_client()
    system, user = build_closing_prompt(company, position)
    result, _ = await llm.chat_json(system=system, user=user, schema=_ClosingText, temperature=0.3)
    assert isinstance(result, _ClosingText)

    turn_id = next_turn_id(transcript)
    closing_turn = Turn(
        turn_id=turn_id,
        role="interviewer",
        content=result.content,
        stage="closing",
        intent="面试结束语",
    )

    log.info("closing_node.done")
    return {
        "transcript": [closing_turn],
        "current_stage": "closing",
        "stage_history": ["closing"],
    }
