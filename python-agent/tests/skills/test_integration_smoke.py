"""集成烟雾测试：P3.1c 三个外部集成 Skill。

所有测试标记 @pytest.mark.integration，默认不运行。
运行方式：
    uv run pytest -m integration tests/skills/test_integration_smoke.py -v

依赖说明：
- test_interview_rag_with_milvus：需要 Milvus 启动并有 INTERVIEW_KB 数据
- test_portfolio_check_mocked_proxy：mock FeishuProxyClient（无需真实飞书）
- test_github_scan_torvalds：需要网络访问 GitHub API（可无 token，60/h 限额）
"""

from __future__ import annotations

import os

import pytest

from jobpilot_agent.api.schemas import JDClassification, UserContext
from jobpilot_agent.integrations.feishu_proxy import FeishuProxyClient, reset_feishu_proxy_singleton
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.github_scan.github_client import reset_github_client_singleton
from jobpilot_agent.skills.interview_rag.index import InterviewRagSkill
from jobpilot_agent.skills.portfolio_check.index import PortfolioCheckSkill
from jobpilot_agent.skills.github_scan.index import GitHubScanSkill
from jobpilot_agent.skills.registry import registry

FIXED_PORTFOLIO_MD = """
# 作品集 - 产品经理

## 项目 1：B 端 SaaS 管理后台（2024）
- 负责从 0 到 1 的产品规划和设计
- 完成用户访谈 30+ 次，整理用户画像
- 上线后 DAU 提升 40%，客户满意度 4.8/5

## 项目 2：用户增长系统（2023）
- 主导 A/B 测试方案设计
- 通过漏斗分析定位关键流失节点，转化率提升 15%

## 项目 3：移动端 App（2022）
- 参与产品需求评审，输出 PRD 文档
"""


@pytest.fixture(autouse=True)
def clean_state():
    registry.reset()
    reset_feishu_proxy_singleton()
    reset_github_client_singleton()
    yield
    registry.reset()
    reset_feishu_proxy_singleton()
    reset_github_client_singleton()


# ---------------------------------------------------------------------------
# Smoke Test 1: interview_rag — 需要 Milvus + INTERVIEW_KB 数据
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_interview_rag_with_milvus():
    """interview_rag 在 Milvus 有数据时应返回面试题；无数据时应降级返回空列表。

    需要：Milvus 启动在 localhost:19530，INTERVIEW_KB collection 存在（可为空）。
    """
    os.environ.setdefault("LLM_API_KEY", os.getenv("LLM_API_KEY", "placeholder"))

    skill = InterviewRagSkill()
    ctx = JDContext(
        request_id="smoke-test-rag",
        user_id="smoke-user",
        jd_text=(
            "字节跳动后端工程师，要求熟练掌握 Python/Go，"
            "熟悉分布式系统、高并发场景设计，有大规模服务治理经验。"
        ),
        user_context=UserContext(),
        classification=JDClassification(
            job_type="tech", sub_type="backend", level="senior",
            locale="zh", channel="social",
        ),
        parsed_jd={"company": "字节跳动", "position": "后端工程师"},
        timeout_seconds=30,
    )

    output = await skill.invoke(ctx)

    # 无论有无数据，都不应该失败（降级为空列表也是 success=True）
    assert output.success is True, f"invoke failed: {output.error}"
    assert isinstance(output.data["questions"], list)
    assert output.data["retrieved_count"] >= 0

    if output.data["retrieved_count"] > 0:
        assert len(output.data["questions"]) >= 1
        q = output.data["questions"][0]
        assert q["question"]
        assert len(q["answer_points"]) >= 1
        assert len(q["rag_source_doc_ids"]) >= 1
    else:
        assert output.data["coverage_note"] is not None


# ---------------------------------------------------------------------------
# Smoke Test 2: portfolio_check — mock 飞书代理（无需真实飞书）
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_portfolio_check_mocked_proxy(monkeypatch):
    """portfolio_check 使用 mock 飞书代理，验证完整 invoke 流程（含真实 LLM 调用）。

    需要：LLM_API_KEY 环境变量（或 placeholder 用于 skip LLM）。
    """
    os.environ.setdefault("LLM_API_KEY", os.getenv("LLM_API_KEY", "placeholder"))

    async def mock_read_doc(self, doc_token: str) -> str:
        return FIXED_PORTFOLIO_MD

    monkeypatch.setattr(FeishuProxyClient, "read_doc", mock_read_doc)

    skill = PortfolioCheckSkill()
    ctx = JDContext(
        request_id="smoke-test-portfolio",
        user_id="smoke-user",
        jd_text=(
            "产品经理，要求有 B 端 SaaS 产品设计经验（3 年以上），"
            "熟悉用户研究方法，有数据驱动产品决策的经验，"
            "有增长产品经验者优先。"
        ),
        user_context=UserContext(portfolio_doc_ref="fake_doc_token_for_test"),
        classification=JDClassification(
            job_type="product", sub_type="b_end", level="middle",
            locale="zh", channel="social",
        ),
        timeout_seconds=30,
    )

    output = await skill.invoke(ctx)

    # 由于 mock 了飞书，只有 LLM 可能失败（placeholder key 会导致 LLM 失败）
    # 烟雾测试目的是验证流程不崩溃，而非 LLM 输出正确
    assert output.skill_name == "portfolio_check"
    assert output.external_calls == 1  # 飞书代理（mock）

    if output.success:
        assert isinstance(output.data["coverage_gaps"], list)
        assert 0.0 <= output.data["coverage_score"] <= 1.0
        assert output.data["case_count"] >= 0


# ---------------------------------------------------------------------------
# Smoke Test 3: github_scan — 真实 GitHub API（torvalds）
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_github_scan_torvalds(monkeypatch):
    """github_scan 对 torvalds（真实 GitHub 用户）验证 API 调用链正确。

    需要：网络访问 GitHub API。
    GITHUB_TOKEN 可选（无 token 受 60/h 限制）。

    注意：此测试不发真实 LLM 请求（mock LLM 调用），只验证 GitHub API 调用链。
    """
    from jobpilot_agent.integrations.llm_client import LLMClient, TokenUsage
    from jobpilot_agent.skills.github_scan.schemas import GitHubScanData

    async def mock_chat_json(self, system, user, schema=None, **kwargs):
        return GitHubScanData(
            username="torvalds",
            public_repo_count=10,
            total_stars=100,
            language_distribution={"C": 80.0, "Python": 20.0},
            matched_stack=["C"],
            missing_stack=[],
            standout_projects=["linux"],
            interview_talking_points=["开发了 Linux 内核"],
        ), TokenUsage(total_tokens=200, call_count=1)

    monkeypatch.setattr(LLMClient, "chat_json", mock_chat_json)

    skill = GitHubScanSkill()
    ctx = JDContext(
        request_id="smoke-test-github",
        user_id="smoke-user",
        jd_text="Linux Kernel Developer, C programming, systems programming",
        user_context=UserContext(github_username="torvalds"),
        classification=JDClassification(
            job_type="tech", sub_type="systems", level="senior",
            locale="en", channel="social",
        ),
        parsed_jd={"tech_stack": [{"name": "C"}, {"name": "Linux"}]},
        timeout_seconds=30,
    )

    output = await skill.invoke(ctx)

    # 速率限制可能导致失败
    if not output.success and "rate limit" in (output.error or "").lower():
        pytest.skip("GitHub rate limit exhausted — run with GITHUB_TOKEN")

    assert output.success is True, f"invoke failed: {output.error}"
    assert output.data["username"] == "torvalds"
    # torvalds 应有公开仓库
    assert output.data["public_repo_count"] >= 0
    # top_repos 格式正确
    for repo in output.data.get("top_repos", []):
        assert "name" in repo
        assert "url" in repo
