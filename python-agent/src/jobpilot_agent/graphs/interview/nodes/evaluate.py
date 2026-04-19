"""evaluate_performance_node：聚合表现信号并生成整体复盘报告。"""

from __future__ import annotations

from jobpilot_agent.graphs.interview.prompts.evaluate import build_report_prompt
from jobpilot_agent.graphs.interview.state import (
    CandidateProfile,
    InterviewReport,
    InterviewState,
    PerformanceSignal,
)
from jobpilot_agent.graphs.interview.transcript import format_transcript_for_llm
from jobpilot_agent.integrations.llm_client import get_llm_client
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


def _aggregate_signals(signals: list[PerformanceSignal]) -> dict[str, float]:
    """按 stage 计算各维度均分，返回 {stage: avg_score}。"""
    from collections import defaultdict

    stage_scores: dict[str, list[float]] = defaultdict(list)
    for s in signals:
        stage_scores[s.stage].append(s.score)
    return {stage: sum(scores) / len(scores) for stage, scores in stage_scores.items()}


async def evaluate_performance_node(state: InterviewState) -> dict[str, object]:
    """汇总面试全程信号，生成 InterviewReport。"""
    transcript = list(state.get("transcript") or [])
    signals: list[PerformanceSignal] = list(state.get("performance_signals") or [])

    stage_avg = _aggregate_signals(signals)
    signals_summary = "\n".join(f"- {stage}: {avg:.1f}" for stage, avg in stage_avg.items()) or "（无信号）"

    profile_raw = state.get("candidate_profile")
    if profile_raw:
        profile = CandidateProfile.model_validate(profile_raw)
        profile_summary = (
            f"用户：{profile.user_id}\n"
            f"简历摘要：{profile.resume_summary}\n"
            f"技术优势：{', '.join(profile.tech_strengths)}"
        )
    else:
        profile_summary = "（档案缺失）"

    transcript_text = format_transcript_for_llm(transcript, last_n=40)

    llm = get_llm_client()
    system, user = build_report_prompt(transcript_text, signals_summary, profile_summary)
    result, _ = await llm.chat_json(system=system, user=user, schema=InterviewReport, temperature=0.0)
    assert isinstance(result, InterviewReport)

    log.info("evaluate_performance_node.done", stages=list(stage_avg.keys()))
    return {
        "report": result.model_dump(),
        "stage_history": ["evaluate"],
    }
