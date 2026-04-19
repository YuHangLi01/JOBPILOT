"""单元测试：github_scan Skill。

覆盖：
- should_invoke 正/反例（level / job_type / github_username）
- invoke 正常路径
- invoke 用户不存在（404）→ SKILL_INPUT_INVALID
- invoke 其他 HTTP 错误 → SKILL_EXTERNAL_FAIL
- invoke 速率限制 → SKILL_EXTERNAL_FAIL
- invoke LLM 超时
- invoke 不抛异常保证
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from jobpilot_agent.api.schemas import JDClassification, UserContext
from jobpilot_agent.integrations.llm_client import LLMClient, TokenUsage
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.github_scan.github_client import GitHubClient, reset_github_client_singleton
from jobpilot_agent.skills.github_scan.index import GitHubScanSkill
from jobpilot_agent.skills.github_scan.schemas import GitHubRepo, GitHubScanData
from jobpilot_agent.skills.registry import registry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_registry():
    registry.reset()
    reset_github_client_singleton()
    yield
    registry.reset()
    reset_github_client_singleton()


@pytest.fixture()
def skill():
    return GitHubScanSkill()


def make_ctx(
    level: str = "senior",
    job_type: str = "tech",
    github_username: str | None = "octocat",
) -> JDContext:
    return JDContext(
        request_id="test-req",
        user_id="test-user",
        jd_text="Python 后端 Senior 工程师，要求熟练使用 FastAPI、PostgreSQL",
        user_context=UserContext(github_username=github_username),
        classification=JDClassification(
            job_type=job_type,  # type: ignore[arg-type]
            sub_type="backend",
            level=level,  # type: ignore[arg-type]
            locale="zh",
            channel="social",
        ),
        parsed_jd={"tech_stack": [{"name": "Python"}, {"name": "FastAPI"}, {"name": "PostgreSQL"}]},
    )


FAKE_USER_INFO = {
    "login": "octocat",
    "public_repos": 10,
    "followers": 100,
    "bio": "Developer",
}

FAKE_REPOS = [
    {
        "name": "hello-world",
        "description": "My first repo",
        "stargazers_count": 5,
        "language": "Python",
        "fork": False,
        "pushed_at": "2025-12-01T00:00:00Z",
        "html_url": "https://github.com/octocat/hello-world",
    },
    {
        "name": "fastapi-demo",
        "description": "FastAPI example",
        "stargazers_count": 20,
        "language": "Python",
        "fork": False,
        "pushed_at": "2025-11-01T00:00:00Z",
        "html_url": "https://github.com/octocat/fastapi-demo",
    },
]


def fake_scan_data() -> GitHubScanData:
    return GitHubScanData(
        username="octocat",
        public_repo_count=10,
        total_stars=25,
        top_repos=[
            GitHubRepo(
                name="fastapi-demo",
                description="FastAPI example",
                stars=20,
                primary_language="Python",
                recent_activity=True,
                url="https://github.com/octocat/fastapi-demo",
                readme_summary="FastAPI + PostgreSQL demo project",
            )
        ],
        language_distribution={"Python": 85.0, "Shell": 15.0},
        matched_stack=["Python", "FastAPI"],
        missing_stack=["PostgreSQL"],
        standout_projects=["fastapi-demo"],
        interview_talking_points=["在 fastapi-demo 中实现了 RESTful API..."],
    )


# ---------------------------------------------------------------------------
# should_invoke 测试
# ---------------------------------------------------------------------------


def test_should_invoke_senior_tech_with_username(skill):
    """tech + senior + github_username → True。"""
    ctx = make_ctx(level="senior", job_type="tech")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_lead_level(skill):
    """lead 级别也应触发。"""
    ctx = make_ctx(level="lead")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_middle_level_skipped(skill):
    """middle 级别不触发（经验不足）。"""
    ctx = make_ctx(level="middle")
    assert skill.should_invoke(ctx) is False


def test_should_invoke_junior_level_skipped(skill):
    """junior 级别不触发。"""
    ctx = make_ctx(level="junior")
    assert skill.should_invoke(ctx) is False


def test_should_invoke_product_job_skipped(skill):
    """非 tech 岗位不触发。"""
    ctx = make_ctx(job_type="product")
    assert skill.should_invoke(ctx) is False


def test_should_invoke_no_username_skipped(skill):
    """无 github_username → False。"""
    ctx = make_ctx(github_username=None)
    assert skill.should_invoke(ctx) is False


def test_should_invoke_no_classification(skill):
    """classification=None → False。"""
    ctx = JDContext(
        request_id="r", user_id="u", jd_text="jd",
        user_context=UserContext(github_username="octocat"),
        classification=None,
    )
    assert skill.should_invoke(ctx) is False


# ---------------------------------------------------------------------------
# invoke 测试
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_github_client(monkeypatch):
    """创建一个 mock GitHubClient 并注入到 get_github_client()。"""
    client = AsyncMock(spec=GitHubClient)
    client.get_rate_limit_remaining = AsyncMock(return_value=1000)
    client.get_user = AsyncMock(return_value=FAKE_USER_INFO)
    client.list_repos = AsyncMock(return_value=FAKE_REPOS)
    client.get_repo_languages = AsyncMock(return_value={"Python": 10000, "Shell": 2000})
    client.get_readme = AsyncMock(return_value="# FastAPI Demo\nA simple FastAPI project.")
    client.close = AsyncMock()
    client.is_recent = GitHubClient.is_recent  # 静态方法直接用真实实现

    monkeypatch.setattr(
        "jobpilot_agent.skills.github_scan.index.get_github_client",
        lambda: client,
    )
    return client


@pytest.mark.asyncio
async def test_invoke_happy_path(skill, mock_github_client, monkeypatch):
    """正常路径 → success=True，metrics 填充。"""
    expected = fake_scan_data()
    expected_usage = TokenUsage(total_tokens=500, call_count=1)

    async def mock_chat_json(self, system, user, schema=None, **kwargs):
        return expected, expected_usage

    monkeypatch.setattr(LLMClient, "chat_json", mock_chat_json)

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is True
    assert output.skill_name == "github_scan"
    assert output.llm_calls == 1
    assert output.tokens_used == 500
    assert output.data["username"] == "octocat"
    assert len(output.data["matched_stack"]) >= 1


@pytest.mark.asyncio
async def test_invoke_user_not_found(skill, monkeypatch):
    """GitHub 用户不存在（404）→ SKILL_INPUT_INVALID。"""
    client = AsyncMock(spec=GitHubClient)
    client.get_rate_limit_remaining = AsyncMock(return_value=1000)
    client.get_user = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "404 Not Found",
            request=httpx.Request("GET", "https://api.github.com/users/nobody"),
            response=httpx.Response(404),
        )
    )
    client.list_repos = AsyncMock(return_value=[])
    client.close = AsyncMock()

    monkeypatch.setattr(
        "jobpilot_agent.skills.github_scan.index.get_github_client", lambda: client
    )

    ctx = make_ctx(github_username="nonexistent_user_xyz")
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_INPUT_INVALID" in (output.error or "")
    assert "nonexistent_user_xyz" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_rate_limit_exhausted(skill, monkeypatch):
    """速率限制耗尽 → SKILL_EXTERNAL_FAIL。"""
    client = AsyncMock(spec=GitHubClient)
    client.get_rate_limit_remaining = AsyncMock(return_value=3)  # ≤ buffer(5)
    client.close = AsyncMock()

    monkeypatch.setattr(
        "jobpilot_agent.skills.github_scan.index.get_github_client", lambda: client
    )

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_EXTERNAL_FAIL" in (output.error or "")
    assert "rate limit" in (output.error or "").lower()


@pytest.mark.asyncio
async def test_invoke_http_500_error(skill, monkeypatch):
    """GitHub API 返回 500 → SKILL_EXTERNAL_FAIL。"""
    client = AsyncMock(spec=GitHubClient)
    client.get_rate_limit_remaining = AsyncMock(return_value=1000)
    client.get_user = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "500 Server Error",
            request=httpx.Request("GET", "https://api.github.com/users/octocat"),
            response=httpx.Response(500),
        )
    )
    client.list_repos = AsyncMock(return_value=[])
    client.close = AsyncMock()

    monkeypatch.setattr(
        "jobpilot_agent.skills.github_scan.index.get_github_client", lambda: client
    )

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_EXTERNAL_FAIL" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_llm_timeout(skill, mock_github_client, monkeypatch):
    """LLM 超时 → SKILL_TIMEOUT。"""
    async def slow_llm(self, *args, **kwargs):
        await asyncio.sleep(100)

    monkeypatch.setattr(LLMClient, "chat_json", slow_llm)

    ctx = make_ctx()
    ctx.timeout_seconds = 0
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_TIMEOUT" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_does_not_raise(skill, monkeypatch):
    """invoke 永不抛原生异常。"""
    client = AsyncMock(spec=GitHubClient)
    client.get_rate_limit_remaining = AsyncMock(return_value=1000)
    client.get_user = AsyncMock(side_effect=RuntimeError("network failure"))
    client.close = AsyncMock()

    monkeypatch.setattr(
        "jobpilot_agent.skills.github_scan.index.get_github_client", lambda: client
    )

    ctx = make_ctx()
    result = await skill.invoke(ctx)
    assert isinstance(result.success, bool)


def test_self_registration(skill):
    """GitHubScanSkill 可注册到 registry。"""
    registry.register(skill)
    assert registry.get("github_scan") is not None
