"""单元测试：portfolio_check Skill。

覆盖：
- should_invoke 正/反例
- invoke 正常路径
- invoke 飞书代理 HTTP 错误 → SKILL_EXTERNAL_FAIL
- invoke 飞书代理超时
- invoke LLM 超时
- invoke 不抛异常保证
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from jobpilot_agent.api.schemas import JDClassification, UserContext
from jobpilot_agent.integrations.feishu_proxy import FeishuProxyClient
from jobpilot_agent.integrations.llm_client import LLMClient, TokenUsage
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.portfolio_check.index import PortfolioCheckSkill
from jobpilot_agent.skills.portfolio_check.schemas import PortfolioCheckData, PortfolioGap
from jobpilot_agent.skills.registry import registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_registry():
    registry.reset()
    yield
    registry.reset()


@pytest.fixture()
def skill():
    return PortfolioCheckSkill()


def make_ctx(
    job_type: str = "product",
    portfolio_ref: str | None = "doc_token_abc123",
) -> JDContext:
    return JDContext(
        request_id="test-req",
        user_id="test-user",
        jd_text="产品经理岗位，要求有 B 端产品设计经验，熟悉用户研究方法",
        user_context=UserContext(portfolio_doc_ref=portfolio_ref),
        classification=JDClassification(
            job_type=job_type,  # type: ignore[arg-type]
            sub_type="product",
            level="middle",
            locale="zh",
            channel="social",
        ),
    )


FAKE_PORTFOLIO_MD = """
# 我的作品集

## 项目 1：B 端 SaaS 管理平台

负责从 0 到 1 的产品设计，覆盖需求分析、原型设计、用户测试。

### 用户研究
- 访谈 20+ 用户，识别核心痛点
- 完成 A/B 测试，转化率提升 15%

## 项目 2：用户增长工具
涉及数据分析和 GTM 策略制定。
"""


def fake_portfolio_data() -> PortfolioCheckData:
    return PortfolioCheckData(
        portfolio_summary="包含 2 个 B 端产品案例，覆盖从需求分析到上线的完整流程",
        case_count=2,
        coverage_gaps=[
            PortfolioGap(
                jd_requirement="有 B 端产品设计经验",
                covered=True,
                coverage_evidence="负责从 0 到 1 的产品设计，覆盖需求分析、原型设计",
                gap_suggestion=None,
            ),
            PortfolioGap(
                jd_requirement="熟悉用户研究方法",
                covered=True,
                coverage_evidence="访谈 20+ 用户，识别核心痛点",
                gap_suggestion=None,
            ),
        ],
        coverage_score=0.9,
        presentation_tips=["补充具体的数据指标", "增加竞品分析截图"],
    )


# ---------------------------------------------------------------------------
# should_invoke 测试
# ---------------------------------------------------------------------------


def test_should_invoke_product_with_ref(skill):
    """product 岗 + portfolio_doc_ref → True。"""
    ctx = make_ctx(job_type="product")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_design_with_ref(skill):
    """design 岗 + portfolio_doc_ref → True。"""
    ctx = make_ctx(job_type="design")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_tech_skipped(skill):
    """tech 岗 → False（走 github_scan）。"""
    ctx = make_ctx(job_type="tech")
    assert skill.should_invoke(ctx) is False


def test_should_invoke_no_portfolio_ref(skill):
    """无 portfolio_doc_ref → False。"""
    ctx = make_ctx(portfolio_ref=None)
    assert skill.should_invoke(ctx) is False


def test_should_invoke_no_classification(skill):
    """classification=None → False。"""
    ctx = JDContext(
        request_id="r", user_id="u", jd_text="jd",
        user_context=UserContext(portfolio_doc_ref="token"),
        classification=None,
    )
    assert skill.should_invoke(ctx) is False


# ---------------------------------------------------------------------------
# invoke 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_happy_path(skill, monkeypatch):
    """正常路径 → success=True，数据正确。"""
    async def mock_read_doc(self, doc_token):
        return FAKE_PORTFOLIO_MD

    expected = fake_portfolio_data()
    expected_usage = TokenUsage(total_tokens=400, call_count=1)

    async def mock_chat_json(self, system, user, schema=None, **kwargs):
        return expected, expected_usage

    monkeypatch.setattr(FeishuProxyClient, "read_doc", mock_read_doc)
    monkeypatch.setattr(LLMClient, "chat_json", mock_chat_json)

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is True
    assert output.skill_name == "portfolio_check"
    assert output.external_calls == 1
    assert output.llm_calls == 1
    assert output.tokens_used == 400
    assert output.data["coverage_score"] == 0.9
    assert output.data["case_count"] == 2


@pytest.mark.asyncio
async def test_invoke_feishu_http_error(skill, monkeypatch):
    """飞书代理 HTTP 错误 → SKILL_EXTERNAL_FAIL。"""
    async def mock_read_doc(self, doc_token):
        raise httpx.HTTPStatusError(
            "502 Bad Gateway",
            request=httpx.Request("POST", "http://localhost/internal"),
            response=httpx.Response(502),
        )

    monkeypatch.setattr(FeishuProxyClient, "read_doc", mock_read_doc)

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_EXTERNAL_FAIL" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_feishu_value_error(skill, monkeypatch):
    """飞书代理返回 ok=false → ValueError → SKILL_EXTERNAL_FAIL。"""
    async def mock_read_doc(self, doc_token):
        raise ValueError("Feishu API error [DOC_NOT_FOUND]: document not found")

    monkeypatch.setattr(FeishuProxyClient, "read_doc", mock_read_doc)

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_EXTERNAL_FAIL" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_llm_timeout(skill, monkeypatch):
    """LLM 超时 → SKILL_TIMEOUT。"""
    async def mock_read_doc(self, doc_token):
        return FAKE_PORTFOLIO_MD

    async def slow_llm(self, *args, **kwargs):
        await asyncio.sleep(100)

    monkeypatch.setattr(FeishuProxyClient, "read_doc", mock_read_doc)
    monkeypatch.setattr(LLMClient, "chat_json", slow_llm)

    ctx = make_ctx()
    ctx.timeout_seconds = 0
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_TIMEOUT" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_does_not_raise(skill, monkeypatch):
    """invoke 永不抛原生异常。"""
    async def always_fail(self, *args, **kwargs):
        raise RuntimeError("unexpected crash")

    monkeypatch.setattr(FeishuProxyClient, "read_doc", always_fail)

    ctx = make_ctx()
    result = await skill.invoke(ctx)
    assert isinstance(result.success, bool)


def test_self_registration(skill):
    """PortfolioCheckSkill 可注册到 registry。"""
    registry.register(skill)
    assert registry.get("portfolio_check") is not None
