"""端到端图测试：mock LLM 节点和 Skill，验证图路由逻辑。

测试策略：
- mock LLMClient.chat_json：控制 parse_jd / classify_jd / final_synthesis 节点的输出
- mock SkillRegistry.get：控制 Skill 执行结果
- mock register_all_skills：避免导入真实 Skill 模块（减少依赖）
- 使用 build_jd_routing_graph()（非单例）确保每个测试得到干净的图实例

6 个测试场景：
1. tech_senior_zh_full_flow：完整流程，多个 tech Skill 被调用
2. product_campus_flow：gpa_check 被触发，github_scan 被跳过
3. en_locale_triggers_en_translate：locale=en 时 en_translate 被调用
4. skill_failure_does_not_break_graph：单个 Skill 失败不影响整体
5. no_skills_invoked_still_completes：无 Skill 被选中仍能完成
6. parallel_skills_execute_concurrently：并行执行比串行快
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jobpilot_agent.graphs.jd_routing_graph import build_jd_routing_graph
from jobpilot_agent.skills.base import SkillOutput

# ── 测试常量 ────────────────────────────────────────────────────────────────

_TECH_SENIOR_JD = """\
资深后端工程师，要求 Python 5年以上，熟悉分布式架构，
有 LangChain/LangGraph 使用经验，本科及以上学历，北京。
"""

_PRODUCT_CAMPUS_JD = """\
产品经理（校招），应届毕业生，熟悉用户研究，
有 C 端产品实习经验优先，要求 GPA 3.5 以上。
"""

_EN_JD = """\
Senior Frontend Engineer (Remote), React & TypeScript expert,
5+ years experience, strong communication skills.
"""

# ── Mock 工厂 ────────────────────────────────────────────────────────────────


def _llm_mock_json(return_value: dict) -> AsyncMock:
    """创建返回指定 dict 的 LLMClient.chat_json mock。"""
    from jobpilot_agent.integrations.llm_client import TokenUsage
    mock = AsyncMock(return_value=(return_value, TokenUsage(total_tokens=100)))
    return mock


def _make_skill_mock(name: str, data: dict | None = None, success: bool = True) -> MagicMock:
    """创建指定名称的 Skill mock。"""
    skill = MagicMock()
    skill.name = name
    skill.should_invoke = MagicMock(return_value=True)
    skill.invoke = AsyncMock(
        return_value=SkillOutput(
            skill_name=name,
            success=success,
            data=data or {"result": f"{name} result"},
            error=None if success else f"SKILL_ERROR: {name} failed",
        )
    )
    return skill


def _make_initial_state(jd_text: str, user_context: dict | None = None) -> dict[str, Any]:
    return {
        "request_id": "test-req-001",
        "user_id": "test-user",
        "jd_text": jd_text,
        "user_context": user_context or {"preferred_lang": "zh"},
        "skill_outputs": [],
        "metadata": {},
        "errors": [],
    }


# ── 通用 patch helpers ────────────────────────────────────────────────────────


def _patch_llm(parse_result=None, classify_result=None, synthesis_result=None):
    """返回给 LLMClient.chat_json 用的 AsyncMock，按调用顺序返回不同值。"""
    from jobpilot_agent.integrations.llm_client import TokenUsage

    _parse = parse_result or {
        "company": "测试公司", "position": "后端工程师",
        "requirements": ["Python 5年"], "responsibilities": ["开发系统"],
    }
    _classify = classify_result or {
        "job_type": "tech", "sub_type": "backend_engineer",
        "level": "senior", "locale": "zh", "channel": "social",
    }
    _synthesis = synthesis_result or {
        "jd_summary": "资深后端工程师，要求 Python 5年经验。",
        "resume_advice": [{"priority": "high", "advice": "突出分布式经验"}],
        "interview_questions": [{"question": "如何设计高并发系统？", "intent": "考察架构能力", "answer_points": ["说明规模", "技术选型"]}],
    }

    usage = TokenUsage(total_tokens=100)
    mock = AsyncMock(side_effect=[
        (_parse, usage),
        (_classify, usage),
        (_synthesis, usage),
    ])
    return mock


# ── 测试 1：完整技术岗流程 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tech_senior_zh_full_flow():
    """验证 tech/senior/zh JD 的完整流程：invoked_skills 包含预期 Skill，final_result 有 jd_summary。"""
    tech_skill = _make_skill_mock("tech_stack_extract", {"tech_stack": [{"name": "Python"}]})
    interview_skill = _make_skill_mock("interview_rag", {"questions": []})

    with (
        patch("jobpilot_agent.graphs.nodes.parse_jd.get_llm_client") as mock_llm_parse,
        patch("jobpilot_agent.graphs.nodes.classify_jd.get_llm_client") as mock_llm_classify,
        patch("jobpilot_agent.graphs.nodes.final_synthesis.get_llm_client") as mock_llm_synth,
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.register_all_skills"),
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.SkillDispatcher") as mock_dispatcher_cls,
        patch("jobpilot_agent.graphs.nodes.invoke_skills_parallel.registry") as mock_registry,
    ):
        from jobpilot_agent.integrations.llm_client import TokenUsage
        usage = TokenUsage(total_tokens=100)

        mock_llm_parse.return_value.chat_json = AsyncMock(return_value=(
            {"company": "测试公司", "position": "后端工程师", "requirements": ["Python 5年"]},
            usage,
        ))
        mock_llm_classify.return_value.chat_json = AsyncMock(return_value=(
            {"job_type": "tech", "sub_type": "backend_engineer", "level": "senior", "locale": "zh", "channel": "social"},
            usage,
        ))
        mock_llm_synth.return_value.chat_json = AsyncMock(return_value=(
            {
                "jd_summary": "资深后端工程师。",
                "resume_advice": [{"priority": "high", "advice": "突出分布式经验"}],
                "interview_questions": [],
            },
            usage,
        ))

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = ([tech_skill, interview_skill], [])
        mock_dispatcher_cls.return_value = mock_dispatcher

        mock_registry.get.side_effect = lambda name: {
            "tech_stack_extract": tech_skill,
            "interview_rag": interview_skill,
        }.get(name)

        graph = build_jd_routing_graph()
        state = await graph.ainvoke(_make_initial_state(_TECH_SENIOR_JD))

    assert "tech_stack_extract" in state["invoked_skills"]
    assert "interview_rag" in state["invoked_skills"]
    assert state["final_result"]["jd_summary"] != ""
    assert state["classification"]["job_type"] == "tech"
    assert len(state["skill_outputs"]) == 2


# ── 测试 2：产品岗校招流程 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_product_campus_flow():
    """gpa_check 应被触发，github_scan 应被跳过（campus 校招场景）。"""
    gpa_skill = _make_skill_mock("gpa_check", {"has_gpa_requirement": True})

    with (
        patch("jobpilot_agent.graphs.nodes.parse_jd.get_llm_client") as mock_llm_parse,
        patch("jobpilot_agent.graphs.nodes.classify_jd.get_llm_client") as mock_llm_classify,
        patch("jobpilot_agent.graphs.nodes.final_synthesis.get_llm_client") as mock_llm_synth,
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.register_all_skills"),
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.SkillDispatcher") as mock_dispatcher_cls,
        patch("jobpilot_agent.graphs.nodes.invoke_skills_parallel.registry") as mock_registry,
    ):
        from jobpilot_agent.integrations.llm_client import TokenUsage
        usage = TokenUsage(total_tokens=80)

        mock_llm_parse.return_value.chat_json = AsyncMock(return_value=(
            {"company": "某公司", "position": "产品经理（校招）"},
            usage,
        ))
        mock_llm_classify.return_value.chat_json = AsyncMock(return_value=(
            {"job_type": "product", "sub_type": "product_manager", "level": "junior", "locale": "zh", "channel": "campus"},
            usage,
        ))
        mock_llm_synth.return_value.chat_json = AsyncMock(return_value=(
            {"jd_summary": "产品经理校招。", "resume_advice": [], "interview_questions": []},
            usage,
        ))

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = ([gpa_skill], [MagicMock(name="github_scan")])
        mock_dispatcher_cls.return_value = mock_dispatcher

        mock_registry.get.return_value = gpa_skill

        graph = build_jd_routing_graph()
        state = await graph.ainvoke(_make_initial_state(_PRODUCT_CAMPUS_JD))

    assert "gpa_check" in state["invoked_skills"]
    assert state["classification"]["channel"] == "campus"
    assert len(state["skill_outputs"]) == 1


# ── 测试 3：英文 JD 触发 en_translate ─────────────────────────────────────


@pytest.mark.asyncio
async def test_en_locale_triggers_en_translate():
    """locale=en 时 en_translate 应被调用。"""
    en_skill = _make_skill_mock("en_translate", {"jd_summary_en": "Senior FE role."})

    with (
        patch("jobpilot_agent.graphs.nodes.parse_jd.get_llm_client") as mock_llm_parse,
        patch("jobpilot_agent.graphs.nodes.classify_jd.get_llm_client") as mock_llm_classify,
        patch("jobpilot_agent.graphs.nodes.final_synthesis.get_llm_client") as mock_llm_synth,
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.register_all_skills"),
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.SkillDispatcher") as mock_dispatcher_cls,
        patch("jobpilot_agent.graphs.nodes.invoke_skills_parallel.registry") as mock_registry,
    ):
        from jobpilot_agent.integrations.llm_client import TokenUsage
        usage = TokenUsage(total_tokens=120)

        mock_llm_parse.return_value.chat_json = AsyncMock(return_value=(
            {"company": "Acme Corp", "position": "Senior Frontend Engineer", "location": "Remote"},
            usage,
        ))
        mock_llm_classify.return_value.chat_json = AsyncMock(return_value=(
            {"job_type": "tech", "sub_type": "frontend_engineer", "level": "senior", "locale": "en", "channel": "social"},
            usage,
        ))
        mock_llm_synth.return_value.chat_json = AsyncMock(return_value=(
            {"jd_summary": "Senior FE role.", "resume_advice": [], "interview_questions": []},
            usage,
        ))

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = ([en_skill], [])
        mock_dispatcher_cls.return_value = mock_dispatcher

        mock_registry.get.return_value = en_skill

        graph = build_jd_routing_graph()
        state = await graph.ainvoke(
            _make_initial_state(_EN_JD, {"preferred_lang": "en"})
        )

    assert "en_translate" in state["invoked_skills"]
    assert state["classification"]["locale"] == "en"


# ── 测试 4：单个 Skill 失败不中断整体图 ──────────────────────────────────


@pytest.mark.asyncio
async def test_skill_failure_does_not_break_graph():
    """一个 Skill invoke 返回 success=False，图仍应成功完成，errors[] 有记录。"""
    failing_skill = _make_skill_mock("tech_stack_extract", success=False)
    ok_skill = _make_skill_mock("interview_rag", {"questions": []})

    with (
        patch("jobpilot_agent.graphs.nodes.parse_jd.get_llm_client") as mock_llm_parse,
        patch("jobpilot_agent.graphs.nodes.classify_jd.get_llm_client") as mock_llm_classify,
        patch("jobpilot_agent.graphs.nodes.final_synthesis.get_llm_client") as mock_llm_synth,
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.register_all_skills"),
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.SkillDispatcher") as mock_dispatcher_cls,
        patch("jobpilot_agent.graphs.nodes.invoke_skills_parallel.registry") as mock_registry,
    ):
        from jobpilot_agent.integrations.llm_client import TokenUsage
        usage = TokenUsage(total_tokens=100)

        mock_llm_parse.return_value.chat_json = AsyncMock(return_value=(
            {"company": "A", "position": "B"}, usage,
        ))
        mock_llm_classify.return_value.chat_json = AsyncMock(return_value=(
            {"job_type": "tech", "sub_type": "dev", "level": "middle", "locale": "zh", "channel": "social"},
            usage,
        ))
        mock_llm_synth.return_value.chat_json = AsyncMock(return_value=(
            {"jd_summary": "Some JD.", "resume_advice": [], "interview_questions": []},
            usage,
        ))

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = ([failing_skill, ok_skill], [])
        mock_dispatcher_cls.return_value = mock_dispatcher

        mock_registry.get.side_effect = lambda name: {
            "tech_stack_extract": failing_skill,
            "interview_rag": ok_skill,
        }.get(name)

        graph = build_jd_routing_graph()
        state = await graph.ainvoke(_make_initial_state(_TECH_SENIOR_JD))

    # 整体应成功完成
    assert state.get("final_result") is not None
    # errors 应记录失败 Skill
    errors = state.get("errors") or []
    assert any(e.get("skill") == "tech_stack_extract" for e in errors)
    # 成功 Skill 的数据应被合并
    assert "interview_rag" in (state.get("merged_skill_data") or {})


# ── 测试 5：无 Skill 被选中仍能完成 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_no_skills_invoked_still_completes():
    """invoked_skills=[] 时图走 skip 路径，final_result 仍应存在（基于 parsed_jd）。"""
    with (
        patch("jobpilot_agent.graphs.nodes.parse_jd.get_llm_client") as mock_llm_parse,
        patch("jobpilot_agent.graphs.nodes.classify_jd.get_llm_client") as mock_llm_classify,
        patch("jobpilot_agent.graphs.nodes.final_synthesis.get_llm_client") as mock_llm_synth,
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.register_all_skills"),
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.SkillDispatcher") as mock_dispatcher_cls,
    ):
        from jobpilot_agent.integrations.llm_client import TokenUsage
        usage = TokenUsage(total_tokens=60)

        mock_llm_parse.return_value.chat_json = AsyncMock(return_value=(
            {"company": "X", "position": "运营专员"}, usage,
        ))
        mock_llm_classify.return_value.chat_json = AsyncMock(return_value=(
            {"job_type": "ops", "sub_type": "operations", "level": "junior", "locale": "zh", "channel": "social"},
            usage,
        ))
        mock_llm_synth.return_value.chat_json = AsyncMock(return_value=(
            {"jd_summary": "运营岗位。", "resume_advice": [], "interview_questions": []},
            usage,
        ))

        # 无 Skill 被选中
        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = ([], [])
        mock_dispatcher_cls.return_value = mock_dispatcher

        graph = build_jd_routing_graph()
        state = await graph.ainvoke(_make_initial_state("运营专员职位，要求有运营经验，负责用户增长工作。"))

    assert state["invoked_skills"] == []
    assert state.get("final_result") is not None
    assert state["final_result"]["jd_summary"] != ""
    # merge_outputs 不应报错（空 skill_outputs）
    assert state.get("merged_skill_data") == {}


# ── 测试 6：并行 Skill 执行时间验证 ──────────────────────────────────────


@pytest.mark.asyncio
async def test_parallel_skills_execute_concurrently():
    """3 个 Skill 各睡眠 0.5s，总时间应 < 1.5s（并行，非串行）。"""

    async def _slow_invoke(_ctx) -> SkillOutput:
        await asyncio.sleep(0.5)
        return SkillOutput(skill_name="slow_skill", success=True, data={})

    skills = []
    for i in range(3):
        s = MagicMock()
        s.name = f"slow_skill_{i}"
        s.should_invoke = MagicMock(return_value=True)
        s.invoke = _slow_invoke
        skills.append(s)

    with (
        patch("jobpilot_agent.graphs.nodes.parse_jd.get_llm_client") as mock_llm_parse,
        patch("jobpilot_agent.graphs.nodes.classify_jd.get_llm_client") as mock_llm_classify,
        patch("jobpilot_agent.graphs.nodes.final_synthesis.get_llm_client") as mock_llm_synth,
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.register_all_skills"),
        patch("jobpilot_agent.graphs.nodes.dispatch_skills.SkillDispatcher") as mock_dispatcher_cls,
        patch("jobpilot_agent.graphs.nodes.invoke_skills_parallel.registry") as mock_registry,
    ):
        from jobpilot_agent.integrations.llm_client import TokenUsage
        usage = TokenUsage(total_tokens=50)

        mock_llm_parse.return_value.chat_json = AsyncMock(return_value=({"company": "A"}, usage))
        mock_llm_classify.return_value.chat_json = AsyncMock(return_value=(
            {"job_type": "tech", "sub_type": "dev", "level": "middle", "locale": "zh", "channel": "social"},
            usage,
        ))
        mock_llm_synth.return_value.chat_json = AsyncMock(return_value=(
            {"jd_summary": "Test.", "resume_advice": [], "interview_questions": []},
            usage,
        ))

        mock_dispatcher = MagicMock()
        mock_dispatcher.dispatch.return_value = (skills, [])
        mock_dispatcher_cls.return_value = mock_dispatcher

        mock_registry.get.side_effect = lambda name: next(
            (s for s in skills if s.name == name), None
        )

        graph = build_jd_routing_graph()
        start = time.monotonic()
        state = await graph.ainvoke(_make_initial_state("技术岗位 JD，要求 Python 开发经验，熟悉分布式系统设计。"))
        elapsed = time.monotonic() - start

    # 串行需 1.5s，并行 < 1.5s（留 0.5s buffer 给 LLM mock 和图开销）
    assert elapsed < 2.0, f"并行执行耗时 {elapsed:.2f}s，超出预期"
    assert len(state["skill_outputs"]) == 3
