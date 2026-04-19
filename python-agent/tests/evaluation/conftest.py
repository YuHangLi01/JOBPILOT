"""评估单测共享 fixtures。"""

from __future__ import annotations

import pytest

from jobpilot_agent.evaluation.runners.scenario_a_runner import RunRecord


ALL_SKILLS = ["tech_stack_extract", "gpa_check", "en_translate", "interview_rag", "portfolio_check", "github_scan"]


def make_record(
    jd_id: str = "jd001",
    predicted_job_type: str = "tech",
    predicted_level: str = "senior",
    predicted_locale: str = "zh",
    predicted_channel: str = "social",
    predicted_sub_type: str = "backend_engineer",
    true_job_type: str = "tech",
    true_level: str = "senior",
    true_locale: str = "zh",
    true_channel: str = "social",
    true_sub_type: str = "backend_engineer",
    invoked_skills: list[str] | None = None,
    expected_skills: list[str] | None = None,
    forbidden_skills: list[str] | None = None,
    latency_ms: int = 3000,
    per_node_ms: dict | None = None,
    total_tokens: int = 1500,
    llm_calls: int = 3,
    success: bool = True,
) -> RunRecord:
    return RunRecord(
        jd_id=jd_id,
        run_label="main",
        jd_text_len=500,
        ground_truth_labels={
            "job_type": true_job_type,
            "sub_type": true_sub_type,
            "level": true_level,
            "locale": true_locale,
            "channel": true_channel,
        },
        ground_truth_expected_skills=expected_skills or ["tech_stack_extract", "interview_rag"],
        ground_truth_forbidden_skills=forbidden_skills or ["gpa_check", "en_translate"],
        predicted_classification={
            "job_type": predicted_job_type,
            "sub_type": predicted_sub_type,
            "level": predicted_level,
            "locale": predicted_locale,
            "channel": predicted_channel,
        },
        predicted_invoked_skills=invoked_skills if invoked_skills is not None else ["tech_stack_extract", "interview_rag"],
        predicted_skipped_skills=[],
        total_latency_ms=latency_ms,
        per_node_latency_ms=per_node_ms or {
            "parse_jd": 800,
            "classify_jd": 600,
            "dispatch_skills": 10,
            "invoke_skills_parallel": 1200,
            "merge_outputs": 5,
            "final_synthesis": 700,
        },
        total_tokens=total_tokens,
        llm_calls=llm_calls,
        success=success,
    )
