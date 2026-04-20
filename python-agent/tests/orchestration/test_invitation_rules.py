"""should_invite_interview 规则函数单元测试（不依赖外部服务）。"""

from __future__ import annotations

import pytest

from jobpilot_agent.graphs.nodes.final_synthesis import (
    _build_interview_invitation,
    _should_invite_interview,
)


def _rag_output(retrieved_count: int = 5, success: bool = True) -> dict:
    return {
        "skill_name": "interview_rag",
        "success": success,
        "data": {"retrieved_count": retrieved_count},
    }


def _other_output(success: bool = True) -> dict:
    return {"skill_name": "tech_stack_extract", "success": success, "data": {}}


# ── should_invite_interview ─────────────────────────────────────────────────


def test_invite_when_rag_succeeds():
    assert _should_invite_interview(
        classification={"job_type": "tech", "level": "middle"},
        skill_outputs=[_other_output(), _rag_output(retrieved_count=5)],
        errors=[],
    )


def test_no_invite_when_errors_present():
    assert not _should_invite_interview(
        classification={"job_type": "tech"},
        skill_outputs=[_rag_output()],
        errors=[{"node": "some_node", "error": "boom"}],
    )


def test_no_invite_when_no_successful_skills():
    assert not _should_invite_interview(
        classification={"job_type": "tech"},
        skill_outputs=[_rag_output(success=False)],
        errors=[],
    )


def test_no_invite_when_rag_not_invoked():
    assert not _should_invite_interview(
        classification={"job_type": "tech"},
        skill_outputs=[_other_output()],
        errors=[],
    )


def test_no_invite_when_rag_coverage_low():
    assert not _should_invite_interview(
        classification={"job_type": "tech"},
        skill_outputs=[_other_output(), _rag_output(retrieved_count=2)],
        errors=[],
    )


def test_no_invite_for_mgmt_job_type():
    assert not _should_invite_interview(
        classification={"job_type": "mgmt"},
        skill_outputs=[_other_output(), _rag_output()],
        errors=[],
    )


def test_no_invite_when_skill_outputs_empty():
    assert not _should_invite_interview(
        classification={"job_type": "tech"},
        skill_outputs=[],
        errors=[],
    )


# ── _build_interview_invitation ─────────────────────────────────────────────


def test_build_invitation_contains_company_position():
    inv = _build_interview_invitation(
        classification={"job_type": "tech", "level": "senior"},
        parsed_jd={"company": "字节跳动", "position": "高级前端"},
    )
    assert inv["should_invite"] is True
    assert inv["suggested_company"] == "字节跳动"
    assert inv["suggested_position"] == "高级前端"
    assert "字节跳动" in inv["cta_text"]


def test_build_invitation_senior_adds_scenario_stage():
    inv = _build_interview_invitation(
        classification={"level": "senior"},
        parsed_jd={"company": "A", "position": "B"},
    )
    assert "scenario" in inv["session_seed"]["recommended_focus_stages"]


def test_build_invitation_middle_no_scenario_stage():
    inv = _build_interview_invitation(
        classification={"level": "middle"},
        parsed_jd={"company": "A", "position": "B"},
    )
    assert "scenario" not in inv["session_seed"]["recommended_focus_stages"]


def test_build_invitation_fallback_defaults_when_jd_empty():
    inv = _build_interview_invitation(
        classification={},
        parsed_jd={},
    )
    assert inv["suggested_company"] == "目标公司"
    assert inv["suggested_position"] == "目标岗位"
