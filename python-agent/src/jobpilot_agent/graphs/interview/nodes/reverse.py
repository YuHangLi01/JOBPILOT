"""reverse_node：角色反转阶段——候选人向面试官提问。"""

from __future__ import annotations

from pydantic import BaseModel

from jobpilot_agent.graphs.interview import ask_user_interrupt
from jobpilot_agent.graphs.interview.interviewer_core import (
    InterviewerQuestion,
)
from jobpilot_agent.graphs.interview.prompts.evaluate import build_reverse_answer_prompt
from jobpilot_agent.graphs.interview.state import InterviewState, Turn
from jobpilot_agent.graphs.interview.transcript import next_turn_id
from jobpilot_agent.integrations.llm_client import get_llm_client
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


class _ReverseAnswer(BaseModel):
    content: str


async def reverse_node(state: InterviewState) -> dict[str, object]:
    """角色反转：邀请候选人提问，面试官 LLM 作答。产生 3 条 transcript。"""
    transcript: list[Turn] = list(state.get("transcript") or [])
    company = str(state.get("company", ""))
    position = str(state.get("position", ""))

    invite_q = InterviewerQuestion(
        content="好的，现在到了你提问的环节，你有什么想问我的吗？",
        intent="邀请反问",
        answer_points=[],
    )

    invite_turn_id = next_turn_id(transcript)
    invite_turn = Turn(
        turn_id=invite_turn_id,
        role="interviewer",
        content=invite_q.content,
        stage="reverse",
        intent=invite_q.intent,
    )

    # LangGraph interrupt：挂起等待候选人提问
    candidate_question: str = ask_user_interrupt(invite_q)

    question_turn_id = invite_turn_id + 1
    question_turn = Turn(
        turn_id=question_turn_id,
        role="candidate",
        content=candidate_question,
        stage="reverse",
    )

    # LLM 生成面试官回答
    llm = get_llm_client()
    system, user = build_reverse_answer_prompt(company, position, candidate_question)
    result, _ = await llm.chat_json(system=system, user=user, schema=_ReverseAnswer, temperature=0.7)
    assert isinstance(result, _ReverseAnswer)

    answer_turn_id = question_turn_id + 1
    answer_turn = Turn(
        turn_id=answer_turn_id,
        role="interviewer",
        content=result.content,
        stage="reverse",
        intent="回答候选人问题",
    )

    log.info("reverse_node.done", company=company)
    return {
        "transcript": [invite_turn, question_turn, answer_turn],
        "stage_round_count": {"reverse": 1},
        "current_stage": "closing",
        "stage_history": ["reverse"],
    }
