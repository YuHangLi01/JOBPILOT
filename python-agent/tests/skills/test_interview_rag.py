"""单元测试：interview_rag Skill。

覆盖：
- should_invoke 正/反例
- invoke 正常路径（有检索结果）
- invoke 降级路径（无检索结果）
- invoke 超时
- invoke 通用异常
- 去重逻辑
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from jobpilot_agent.api.schemas import JDClassification, UserContext
from jobpilot_agent.integrations.llm_client import LLMClient, TokenUsage
from jobpilot_agent.retrieval.types import CollectionName, RetrievalResult
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.interview_rag.index import InterviewRagSkill, _dedup_by_doc_id
from jobpilot_agent.skills.interview_rag.schemas import InterviewQuestion, InterviewRagData
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
    return InterviewRagSkill()


def make_ctx(company: str = "字节跳动", position: str = "后端工程师") -> JDContext:
    return JDContext(
        request_id="test-req",
        user_id="test-user",
        jd_text="Python 后端工程师，要求熟悉 Django、Redis",
        user_context=UserContext(),
        classification=JDClassification(
            job_type="tech", sub_type="backend", level="middle",
            locale="zh", channel="social",
        ),
        parsed_jd={"company": company, "position": position},
    )


def make_result(doc_id: str, score: float = 0.8, stage: str = "tech_qa") -> RetrievalResult:
    return RetrievalResult(
        doc_id=doc_id,
        text=f"面试题内容 [{doc_id}]：请介绍 Redis 持久化机制",
        metadata={"company": "字节跳动", "stage": stage},
        score=score,
    )


def fake_rag_data() -> InterviewRagData:
    return InterviewRagData(
        retrieved_count=3,
        questions=[
            InterviewQuestion(
                question="请介绍 Redis 的 RDB 和 AOF 持久化机制的区别",
                source_company="字节跳动",
                source_stage="tech_qa",
                intent="考察候选人对 Redis 持久化机制的理解",
                answer_points=["RDB 是快照，AOF 是追加日志", "RDB 恢复快，AOF 更安全", "通常混合使用"],
                rag_source_doc_ids=["doc-001"],
                rag_score=0.85,
            )
        ],
        coverage_note="命中 3 条相关面经",
    )


# ---------------------------------------------------------------------------
# _dedup_by_doc_id 单元测试
# ---------------------------------------------------------------------------


def test_dedup_keeps_highest_score():
    """去重时保留同 doc_id 中分数最高的结果。"""
    r1 = make_result("doc-001", score=0.9)
    r2 = make_result("doc-001", score=0.7)  # 重复，低分
    r3 = make_result("doc-002", score=0.8)
    result = _dedup_by_doc_id([r1, r2, r3])
    assert len(result) == 2
    doc_ids = [r.doc_id for r in result]
    assert "doc-001" in doc_ids
    # 保留高分副本
    doc1 = next(r for r in result if r.doc_id == "doc-001")
    assert doc1.score == 0.9


# ---------------------------------------------------------------------------
# should_invoke 测试
# ---------------------------------------------------------------------------


def test_should_invoke_with_company_and_position(skill):
    """有 company 和 position → True。"""
    ctx = make_ctx()
    assert skill.should_invoke(ctx) is True


def test_should_invoke_company_only(skill):
    """只有 company → True。"""
    ctx = make_ctx(company="阿里巴巴", position="")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_position_only(skill):
    """只有 position → True。"""
    ctx = make_ctx(company="", position="后端工程师")
    assert skill.should_invoke(ctx) is True


def test_should_invoke_no_parsed_jd(skill):
    """parsed_jd 为空 → False。"""
    ctx = JDContext(
        request_id="r", user_id="u", jd_text="some jd",
        parsed_jd={},
    )
    assert skill.should_invoke(ctx) is False


def test_should_invoke_both_empty(skill):
    """company 和 position 均为空字符串 → False。"""
    ctx = make_ctx(company="", position="")
    assert skill.should_invoke(ctx) is False


# ---------------------------------------------------------------------------
# invoke 测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_happy_path(skill, monkeypatch):
    """正常路径：RAG 有结果，LLM 返回合法数据 → success=True。"""
    results = [make_result("doc-001"), make_result("doc-002", stage="project_deep_dive")]

    async def mock_search(*args, **kwargs):
        return results

    expected_data = fake_rag_data()
    expected_usage = TokenUsage(total_tokens=300, call_count=1)

    async def mock_chat_json(self, system, user, schema=None, **kwargs):
        return expected_data, expected_usage

    monkeypatch.setattr("jobpilot_agent.skills.interview_rag.index.search_interview_kb", mock_search)
    monkeypatch.setattr(LLMClient, "chat_json", mock_chat_json)

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is True
    assert output.skill_name == "interview_rag"
    assert output.external_calls == 2
    assert output.llm_calls == 1
    assert output.tokens_used == 300
    assert len(output.data["questions"]) >= 1


@pytest.mark.asyncio
async def test_invoke_empty_rag_graceful_degradation(skill, monkeypatch):
    """RAG 无结果 → 降级返回空列表 + coverage_note，success=True，不调 LLM。"""
    async def mock_search(*args, **kwargs):
        return []

    llm_called = False

    async def mock_chat_json(self, *args, **kwargs):
        nonlocal llm_called
        llm_called = True
        return InterviewRagData(), TokenUsage()

    monkeypatch.setattr("jobpilot_agent.skills.interview_rag.index.search_interview_kb", mock_search)
    monkeypatch.setattr(LLMClient, "chat_json", mock_chat_json)

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is True
    assert output.data["retrieved_count"] == 0
    assert output.data["questions"] == []
    assert output.data["coverage_note"] is not None
    assert llm_called is False  # LLM 不应被调用


@pytest.mark.asyncio
async def test_invoke_rag_exception(skill, monkeypatch):
    """RAG 检索抛异常 → SKILL_ERROR，不传播。"""
    async def mock_search(*args, **kwargs):
        raise ConnectionError("Milvus unavailable")

    monkeypatch.setattr("jobpilot_agent.skills.interview_rag.index.search_interview_kb", mock_search)

    ctx = make_ctx()
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_ERROR" in (output.error or "")


@pytest.mark.asyncio
async def test_invoke_llm_timeout(skill, monkeypatch):
    """LLM 超时 → SKILL_TIMEOUT，不抛异常。"""
    results = [make_result("doc-001")]

    async def mock_search(*args, **kwargs):
        return results

    async def slow_llm(self, *args, **kwargs):
        await asyncio.sleep(100)

    monkeypatch.setattr("jobpilot_agent.skills.interview_rag.index.search_interview_kb", mock_search)
    monkeypatch.setattr(LLMClient, "chat_json", slow_llm)

    ctx = make_ctx()
    ctx.timeout_seconds = 0
    output = await skill.invoke(ctx)

    assert output.success is False
    assert "SKILL_TIMEOUT" in (output.error or "")


def test_self_registration(skill):
    """InterviewRagSkill 可注册到 registry。"""
    registry.register(skill)
    assert registry.get("interview_rag") is not None
