"""单元测试：tech_stack_extract Skill。

测试策略：
- 不发真实 LLM 请求，通过 monkeypatch mock LLMClient.chat_json
- 每个测试通过 clean_registry fixture 隔离注册表状态
- 覆盖：should_invoke 正/反例、invoke 正常路径、malformed JSON、超时
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from jobpilot_agent.api.schemas import JDClassification, UserContext
from jobpilot_agent.integrations.llm_client import LLMClient, TokenUsage
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.registry import registry
from jobpilot_agent.skills.tech_stack_extract.index import TechStackExtractSkill
from jobpilot_agent.skills.tech_stack_extract.schemas import (
    TechSkillItem,
    TechStackExtractData,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_registry():
    registry.reset()
    yield
    registry.reset()


@pytest.fixture()
def skill() -> TechStackExtractSkill:
    return TechStackExtractSkill()


def make_ctx(
    jd_text: str = "Python 后端工程师，要求熟练掌握 Django、PostgreSQL、Redis，有 Docker 使用经验，" * 5,
    job_type: str = "tech",
    locale: str = "zh",
    channel: str = "social",
) -> JDContext:
    return JDContext(
        request_id="test-req",
        user_id="test-user",
        jd_text=jd_text,
        user_context=UserContext(),
        classification=JDClassification(
            job_type=job_type,  # type: ignore[arg-type]
            sub_type="backend",
            level="middle",
            locale=locale,  # type: ignore[arg-type]
            channel=channel,  # type: ignore[arg-type]
        ),
    )


def fake_tech_data() -> TechStackExtractData:
    return TechStackExtractData(
        tech_stack=[
            TechSkillItem(
                name="Python",
                category="language",
                required=True,
                experience_years=3,
                evidence_quote="熟练掌握 Python",
            ),
            TechSkillItem(
                name="Django",
                category="framework",
                required=True,
                experience_years=None,
                evidence_quote="要求熟练掌握 Django",
            ),
        ],
        primary_language="Python",
        tech_complexity=3,
        summary="Python 后端岗，以 Django + PostgreSQL 为核心",
    )


# ---------------------------------------------------------------------------
# should_invoke 测试
# ---------------------------------------------------------------------------


def test_should_invoke_tech_job_long_jd(skill):
    """技术岗 + 足够长的 JD → True。"""
    ctx = make_ctx(job_type="tech")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_product_job(skill):
    """产品岗（非运营管理）也应触发。"""
    ctx = make_ctx(job_type="product")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_ops_job_skipped(skill):
    """运营岗（ops）→ False。"""
    ctx = make_ctx(job_type="ops")
    assert skill.should_invoke(ctx) is False


def test_should_invoke_mgmt_job_skipped(skill):
    """管理岗（mgmt）→ False。"""
    ctx = make_ctx(job_type="mgmt")
    assert skill.should_invoke(ctx) is False


def test_should_invoke_short_jd_skipped(skill):
    """JD 文本不足 200 字 → False（避免无效调用）。"""
    ctx = make_ctx(jd_text="Python 工程师，要求 3 年经验。")
    assert skill.should_invoke(ctx) is False


def test_should_invoke_no_classification(skill):
    """classification 为 None 时（未分类）→ False（安全兜底）。"""
    ctx = JDContext(
        request_id="r",
        user_id="u",
        jd_text="Python " * 50,
        classification=None,
    )
    assert skill.should_invoke(ctx) is False


# ---------------------------------------------------------------------------
# invoke 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_happy_path(skill, monkeypatch):
    """正常路径：LLM 返回合法数据 → success=True，metrics 填充。"""
    expected = fake_tech_data()
    expected_usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150, call_count=1)

    async def mock_chat_json(self, system, user, schema=None, **kwargs):
        return expected, expected_usage

    monkeypatch.setattr(LLMClient, "chat_json", mock_chat_json)

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is True
    assert output.skill_name == "tech_stack_extract"
    assert output.tokens_used == 150
    assert output.llm_calls == 1
    assert output.latency_ms >= 0
    assert output.data["primary_language"] == "Python"
    assert len(output.data["tech_stack"]) == 2


@pytest.mark.asyncio
async def test_invoke_validation_error(skill, monkeypatch):
    """LLM 返回不符合 schema 的数据 → success=False，error 含 SKILL_LLM_FAIL。"""
    from pydantic import ValidationError

    # 构造真实的 Pydantic ValidationError
    try:
        TechStackExtractData.model_validate({"tech_complexity": "not_an_int_out_of_range"})
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
    """LLM 调用超时 → success=False，error 含 SKILL_TIMEOUT。"""

    async def slow_chat_json(self, system, user, schema=None, **kwargs):
        await asyncio.sleep(100)
        return fake_tech_data(), TokenUsage()

    monkeypatch.setattr(LLMClient, "chat_json", slow_chat_json)

    ctx = make_ctx()
    ctx.timeout_seconds = 0  # 立即超时
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_TIMEOUT" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_generic_exception(skill, monkeypatch):
    """LLM 抛出通用异常 → success=False，error 含 SKILL_ERROR。"""

    async def failing_chat_json(self, system, user, schema=None, **kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr(LLMClient, "chat_json", failing_chat_json)

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_ERROR" in (output.error or "")
    assert "RuntimeError" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_does_not_raise(skill, monkeypatch):
    """invoke 无论发生什么都不抛异常（反模式检测）。"""

    async def always_fail(self, *args, **kwargs):
        raise Exception("critical failure")

    monkeypatch.setattr(LLMClient, "chat_json", always_fail)

    ctx = make_ctx()
    result = await skill.invoke(ctx)
    assert isinstance(result.success, bool)


# ---------------------------------------------------------------------------
# 注册与元数据测试
# ---------------------------------------------------------------------------


def test_skill_metadata():
    """验证 Skill 元数据字段正确。"""
    skill = TechStackExtractSkill()
    assert skill.name == "tech_stack_extract"
    assert skill.metadata.version == "0.1.0"
    assert "llm" in skill.metadata.tags


def test_self_registration():
    """TechStackExtractSkill 实例化后可注册到 registry，name 正确。"""
    s = TechStackExtractSkill()
    registry.register(s)
    assert registry.get("tech_stack_extract") is not None
