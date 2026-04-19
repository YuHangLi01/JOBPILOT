"""节点基础抽象——run_interview_turn 被所有标准面试节点复用。"""

from __future__ import annotations

from jobpilot_agent.graphs.interview import ask_user_interrupt
from jobpilot_agent.graphs.interview.interviewer_core import (
    InterviewerInput,
    get_interviewer_core,
)
from jobpilot_agent.graphs.interview.state import (
    CandidateProfile,
    InterviewStage,
    InterviewState,
    Turn,
)
from jobpilot_agent.graphs.interview.transcript import count_stage_turns, next_turn_id
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


async def run_interview_turn(
    state: InterviewState,
    stage: InterviewStage,
    max_stage_rounds: int = 5,
) -> dict[str, object]:
    """执行一个「面试官出问 → 用户答 → 打分」的完整轮次。

    被 intro_node / project_deep_dive_node / tech_qa_node / scenario_node 复用。
    异常时返回降级 dict（含 errors 字段），不向外传播异常。
    """
    core = get_interviewer_core()
    transcript: list[Turn] = list(state.get("transcript") or [])

    try:
        # 候选人档案（state 中存为 dict，需反序列化）
        profile_raw = state.get("candidate_profile")
        profile = CandidateProfile.model_validate(profile_raw) if profile_raw else None

        stage_round = count_stage_turns(transcript, stage) // 2

        inp = InterviewerInput(
            company=str(state.get("company", "")),
            position=str(state.get("position", "")),
            stage=stage,
            candidate_profile=profile,
            transcript=transcript,
            stage_round=stage_round,
            max_stage_rounds=max_stage_rounds,
        )

        question = await core.generate_next_question(inp)

        q_turn_id = next_turn_id(transcript)
        q_turn = Turn(
            turn_id=q_turn_id,
            role="interviewer",
            content=question.content,
            stage=stage,
            intent=question.intent,
            answer_points=question.answer_points,
            rag_source_doc_ids=question.rag_source_doc_ids,
        )

        # LangGraph interrupt：图在此处挂起，等待 Command(resume=...) 恢复
        user_input: str = ask_user_interrupt(question)

        a_turn_id = q_turn_id + 1
        a_turn = Turn(
            turn_id=a_turn_id,
            role="candidate",
            content=user_input,
            stage=stage,
        )

        signals = await core.evaluate_candidate_answer(
            question=question.content,
            answer=user_input,
            stage=stage,
            question_answer_points=question.answer_points,
            turn_id=a_turn_id,
        )

        log.info(
            "run_interview_turn.done",
            stage=stage,
            round=stage_round,
            signals=len(signals),
        )
        return {
            "transcript": [q_turn, a_turn],
            "stage_round_count": {stage: 1},
            "performance_signals": signals,
            "metadata": {f"{stage}_round_{stage_round}_q_turn_id": q_turn_id},
        }

    except Exception as exc:
        # 不捕获 langgraph.errors.GraphInterrupt（它不是 Exception 的子类）
        log.error("run_interview_turn.error", stage=stage, error=str(exc))
        return {
            "errors": [{"stage": stage, "error": f"{type(exc).__name__}: {exc}"}],
        }
