"""单元测试：gpa_check Skill。

覆盖：
- should_invoke 正/反例（campus vs social，信号词有无）
- regex_rules.extract_gpa_signals() 正确提取各类信号
- invoke 正常路径、ValidationError、超时
- 双路策略（正则信号拼入 LLM prompt）
"""

from __future__ import annotations

import asyncio

import pytest

from jobpilot_agent.api.schemas import JDClassification, UserContext
from jobpilot_agent.integrations.llm_client import LLMClient, TokenUsage
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.gpa_check.index import GPACheckSkill
from jobpilot_agent.skills.gpa_check.regex_rules import (
    extract_gpa_signals,
    has_education_signals,
)
from jobpilot_agent.skills.gpa_check.schemas import EducationRequirement, GPACheckData
from jobpilot_agent.skills.registry import registry


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_registry():
    registry.reset()
    yield
    registry.reset()


@pytest.fixture()
def skill() -> GPACheckSkill:
    return GPACheckSkill()


def make_ctx(
    jd_text: str = "校招招聘，要求985/211毕业，GPA≥3.5/5.0，大三大四在读学生均可投递。",
    channel: str = "campus",
    job_type: str = "tech",
) -> JDContext:
    return JDContext(
        request_id="test-req",
        user_id="test-user",
        jd_text=jd_text,
        user_context=UserContext(),
        classification=JDClassification(
            job_type=job_type,  # type: ignore[arg-type]
            sub_type="backend",
            level="junior",
            locale="zh",
            channel=channel,  # type: ignore[arg-type]
        ),
    )


def fake_gpa_data() -> GPACheckData:
    return GPACheckData(
        requirements=[
            EducationRequirement(
                req_type="gpa",
                value="3.5/5.0",
                required=True,
                implicit=False,
                evidence_quote="GPA≥3.5/5.0",
            ),
            EducationRequirement(
                req_type="school_tier",
                value="985/211",
                required=True,
                implicit=False,
                evidence_quote="要求985/211毕业",
            ),
        ],
        has_gpa_requirement=True,
        has_school_tier_requirement=True,
        min_degree="本科",
        overall_strictness=4,
        notes="显性 GPA 和院校层次要求",
    )


# ---------------------------------------------------------------------------
# regex_rules 单元测试
# ---------------------------------------------------------------------------


def test_has_education_signals_positive():
    """包含 GPA 关键词 → True。"""
    assert has_education_signals("要求GPA≥3.5/5.0") is True


def test_has_education_signals_985():
    """包含 985 → True。"""
    assert has_education_signals("985/211院校毕业") is True


def test_has_education_signals_negative():
    """无任何学历信号 → False。"""
    assert has_education_signals("招聘 Python 工程师，5年经验") is False


def test_extract_gpa_signals_gpa():
    """正则能提取 GPA 门槛数值。"""
    text = "要求GPA≥3.5/5.0，优秀应届生"
    signals = extract_gpa_signals(text)
    assert len(signals["gpa_mentions"]) >= 1
    assert signals["gpa_mentions"][0]["value"] == "3.5/5.0"


def test_extract_gpa_signals_school_tier():
    """正则能提取 985/211 院校层次。"""
    text = "仅限985/211高校毕业"
    signals = extract_gpa_signals(text)
    assert "985" in signals["school_tiers"]
    assert "211" in signals["school_tiers"]


def test_extract_gpa_signals_degree():
    """正则能提取学历层次。"""
    text = "要求硕士及以上学历"
    signals = extract_gpa_signals(text)
    assert "硕士" in signals["degree_mentions"]


# ---------------------------------------------------------------------------
# should_invoke 测试
# ---------------------------------------------------------------------------


def test_should_invoke_campus_with_signals(skill):
    """campus + GPA 信号词 → True。"""
    ctx = make_ctx(channel="campus")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_social_skipped(skill):
    """social 渠道 → False（不分析社招 GPA）。"""
    ctx = make_ctx(channel="social")
    assert skill.should_invoke(ctx) is False


def test_should_invoke_campus_no_signals(skill):
    """campus + 无学历信号词 → False。"""
    jd_text = "应届实习生，欢迎各专业，提供完善的培训体系和晋升通道，工作地点北京" * 3
    ctx = make_ctx(jd_text=jd_text, channel="campus")
    assert skill.should_invoke(ctx) is False


def test_should_invoke_no_classification(skill):
    """classification 为 None → False（安全兜底）。"""
    ctx = JDContext(
        request_id="r",
        user_id="u",
        jd_text="要求985毕业，GPA≥3.5",
        classification=None,
    )
    assert skill.should_invoke(ctx) is False


# ---------------------------------------------------------------------------
# invoke 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_happy_path(skill, monkeypatch):
    """正常路径 → success=True，数据正确填充。"""
    expected = fake_gpa_data()
    expected_usage = TokenUsage(prompt_tokens=80, completion_tokens=120, total_tokens=200, call_count=1)

    async def mock_chat_json(self, system, user, schema=None, **kwargs):
        return expected, expected_usage

    monkeypatch.setattr(LLMClient, "chat_json", mock_chat_json)

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is True
    assert output.skill_name == "gpa_check"
    assert output.tokens_used == 200
    assert output.data["has_gpa_requirement"] is True
    assert output.data["has_school_tier_requirement"] is True
    assert output.data["overall_strictness"] == 4


@pytest.mark.asyncio
async def test_invoke_validation_error(skill, monkeypatch):
    """schema 校验失败 → success=False，error 含 SKILL_LLM_FAIL。"""
    from pydantic import ValidationError

    # 构造真实的 Pydantic ValidationError
    try:
        GPACheckData.model_validate({"overall_strictness": 999})
    except ValidationError as real_ve:
        captured_ve = real_ve

    async def mock_chat_json(self, system, user, schema=None, **kwargs):
        raise captured_ve

    monkeypatch.setattr(LLMClient, "chat_json", mock_chat_json)

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_LLM_FAIL" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_timeout(skill, monkeypatch):
    """LLM 超时 → success=False，error 含 SKILL_TIMEOUT。"""

    async def slow_chat_json(self, system, user, schema=None, **kwargs):
        await asyncio.sleep(100)

    monkeypatch.setattr(LLMClient, "chat_json", slow_chat_json)

    ctx = make_ctx()
    ctx.timeout_seconds = 0
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_TIMEOUT" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_does_not_raise(skill, monkeypatch):
    """invoke 永不抛出原生异常。"""

    async def always_fail(self, *args, **kwargs):
        raise ConnectionError("service unavailable")

    monkeypatch.setattr(LLMClient, "chat_json", always_fail)

    ctx = make_ctx()
    result = await skill.invoke(ctx)
    assert isinstance(result.success, bool)


def test_self_registration():
    """GPACheckSkill 实例化后可注册到 registry，name 正确。"""
    s = GPACheckSkill()
    registry.register(s)
    assert registry.get("gpa_check") is not None
