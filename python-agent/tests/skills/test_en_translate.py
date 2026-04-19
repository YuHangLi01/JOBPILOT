"""单元测试：en_translate Skill。

覆盖：
- should_invoke 正例（locale=en / 外资公司 / preferred_lang=en）
- should_invoke 反例（中文岗 + 国内公司 + 无偏好）
- invoke 正常路径、ValidationError、超时
- FOREIGN_COMPANIES 名单匹配逻辑
"""

from __future__ import annotations

import asyncio

import pytest

from jobpilot_agent.api.schemas import JDClassification, UserContext
from jobpilot_agent.integrations.llm_client import LLMClient, TokenUsage
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.en_translate.index import EnTranslateSkill, _is_foreign_company
from jobpilot_agent.skills.en_translate.schemas import EnTranslateData
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
def skill() -> EnTranslateSkill:
    return EnTranslateSkill()


def make_ctx(
    locale: str = "zh",
    company: str = "某国内公司",
    preferred_lang: str = "zh",
    jd_text: str = "招聘后端工程师，要求熟悉 Python",
) -> JDContext:
    return JDContext(
        request_id="test-req",
        user_id="test-user",
        jd_text=jd_text,
        user_context=UserContext(preferred_lang=preferred_lang),  # type: ignore[arg-type]
        classification=JDClassification(
            job_type="tech",
            sub_type="backend",
            level="middle",
            locale=locale,  # type: ignore[arg-type]
            channel="social",
        ),
        parsed_jd={"company": company},
    )


def fake_en_data() -> EnTranslateData:
    return EnTranslateData(
        jd_summary_en=(
            "We are seeking a skilled Python backend engineer to join our team. "
            "The ideal candidate has 3+ years of experience with Django and PostgreSQL, "
            "strong understanding of RESTful API design, and familiarity with Docker. "
            "You will be responsible for designing and implementing scalable microservices, "
            "collaborating with frontend teams, and maintaining CI/CD pipelines. "
            "This is a full-time role offering competitive compensation."
        ),
        jd_summary_zh=(
            "我们寻找一名经验丰富的 Python 后端工程师，要求熟悉 Django 和 PostgreSQL，"
            "能够设计并实现高扩展性微服务，与前端团队协作，维护 CI/CD 流程。"
        ),
        resume_bullets_en=[
            "Designed and implemented RESTful APIs serving 10M+ daily requests using Django REST Framework",
            "Optimized PostgreSQL query performance by 40% through indexing and query refactoring",
            "Containerized 5 microservices with Docker, reducing deployment time by 60%",
        ],
        key_terms_en=["Python", "Django", "PostgreSQL", "REST API", "Docker", "microservices"],
        tone="formal",
    )


# ---------------------------------------------------------------------------
# _is_foreign_company 辅助函数测试
# ---------------------------------------------------------------------------


def test_is_foreign_company_google():
    """Google 应被识别为外资公司。"""
    assert _is_foreign_company("Google") is True
    assert _is_foreign_company("google china") is True


def test_is_foreign_company_case_insensitive():
    """外资公司名单匹配大小写不敏感。"""
    assert _is_foreign_company("MICROSOFT") is True
    assert _is_foreign_company("Amazon Web Services") is True


def test_is_foreign_company_domestic():
    """国内公司不在名单中。"""
    assert _is_foreign_company("字节跳动") is False
    assert _is_foreign_company("某创业公司") is False


def test_is_foreign_company_none():
    """公司名为 None 时安全返回 False。"""
    assert _is_foreign_company(None) is False


# ---------------------------------------------------------------------------
# should_invoke 测试
# ---------------------------------------------------------------------------


def test_should_invoke_locale_en(skill):
    """locale=en → True。"""
    ctx = make_ctx(locale="en")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_foreign_company(skill):
    """外资公司（Google） → True。"""
    ctx = make_ctx(company="Google LLC", locale="zh")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_preferred_lang_en(skill):
    """用户偏好英文 → True。"""
    ctx = make_ctx(preferred_lang="en", locale="zh")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_domestic_zh(skill):
    """中文岗 + 国内公司 + 中文偏好 → False。"""
    ctx = make_ctx(locale="zh", company="字节跳动", preferred_lang="zh")
    assert skill.should_invoke(ctx) is False


def test_should_invoke_no_classification(skill):
    """classification 为 None 且无外资公司 + 无 en 偏好 → False。"""
    ctx = JDContext(
        request_id="r",
        user_id="u",
        jd_text="Python engineer needed",
        classification=None,
        parsed_jd={"company": "某国内创业公司"},
    )
    assert skill.should_invoke(ctx) is False


# ---------------------------------------------------------------------------
# invoke 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_happy_path(skill, monkeypatch):
    """正常路径 → success=True，数据结构正确。"""
    expected = fake_en_data()
    expected_usage = TokenUsage(prompt_tokens=200, completion_tokens=400, total_tokens=600, call_count=1)

    async def mock_chat_json(self, system, user, schema=None, **kwargs):
        return expected, expected_usage

    monkeypatch.setattr(LLMClient, "chat_json", mock_chat_json)

    ctx = make_ctx(locale="en")
    output = await skill.invoke(ctx)

    assert output.success is True
    assert output.skill_name == "en_translate"
    assert output.tokens_used == 600
    assert output.llm_calls == 1
    assert len(output.data["resume_bullets_en"]) >= 3
    assert len(output.data["key_terms_en"]) >= 5
    assert "Python" in output.data["key_terms_en"]


@pytest.mark.asyncio
async def test_invoke_validation_error(skill, monkeypatch):
    """schema 校验失败 → success=False，error 含 SKILL_LLM_FAIL。"""
    from pydantic import ValidationError

    # 构造真实的 Pydantic ValidationError（缺少必填字段）
    try:
        EnTranslateData.model_validate({})
    except ValidationError as real_ve:
        captured_ve = real_ve

    async def mock_chat_json(self, system, user, schema=None, **kwargs):
        raise captured_ve

    monkeypatch.setattr(LLMClient, "chat_json", mock_chat_json)

    ctx = make_ctx(locale="en")
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_LLM_FAIL" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_timeout(skill, monkeypatch):
    """LLM 超时 → success=False，error 含 SKILL_TIMEOUT。"""

    async def slow_chat_json(self, system, user, schema=None, **kwargs):
        await asyncio.sleep(100)

    monkeypatch.setattr(LLMClient, "chat_json", slow_chat_json)

    ctx = make_ctx(locale="en")
    ctx.timeout_seconds = 0
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_TIMEOUT" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_does_not_raise(skill, monkeypatch):
    """invoke 永不抛出原生异常。"""

    async def always_fail(self, *args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(LLMClient, "chat_json", always_fail)

    ctx = make_ctx(locale="en")
    result = await skill.invoke(ctx)
    assert isinstance(result.success, bool)


@pytest.mark.asyncio
async def test_invoke_call_count_in_metrics(skill, monkeypatch):
    """invoke 正确传递 call_count 到 llm_calls 字段。"""
    expected = fake_en_data()
    expected_usage = TokenUsage(total_tokens=300, call_count=2)

    async def mock_chat_json(self, system, user, schema=None, **kwargs):
        return expected, expected_usage

    monkeypatch.setattr(LLMClient, "chat_json", mock_chat_json)

    ctx = make_ctx(locale="en")
    output = await skill.invoke(ctx)

    assert output.llm_calls == 2


def test_self_registration():
    """EnTranslateSkill 实例化后可注册到 registry，name 正确。"""
    s = EnTranslateSkill()
    registry.register(s)
    assert registry.get("en_translate") is not None


def test_skill_metadata(skill):
    """验证元数据字段。"""
    assert skill.name == "en_translate"
    assert "english" in skill.metadata.tags
    assert skill.metadata.version == "0.1.0"
