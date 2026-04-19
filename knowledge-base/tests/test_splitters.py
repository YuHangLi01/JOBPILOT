"""单元测试：splitter 逻辑不依赖 Milvus 或模型权重。"""

from __future__ import annotations

from pathlib import Path

from kb_builder.ingest.splitters import split_interview, split_jd, split_user_doc
from kb_builder.models import (
    InterviewTurn,
    JDLabels,
    LabeledJD,
    StructuredInterview,
)


def _base_labels() -> JDLabels:
    return JDLabels(
        job_type="tech",
        sub_type="backend",
        level="senior",
        locale="zh",
        channel="social",
    )


# ---------------------------------------------------------------------------
# JD splitter
# ---------------------------------------------------------------------------


def test_split_jd_sectioned() -> None:
    text = (
        "公司：字节跳动\n职位：高级后端工程师\n\n"
        "岗位职责：\n"
        "1. 负责核心后端微服务研发与架构设计。\n"
        "2. 主导跨团队数据链路和消息队列方案落地。\n"
        "3. 参与在线推理系统的性能优化与稳定性保障。\n\n"
        "任职要求：\n"
        "1. 3 年以上 Golang 后端开发经验，熟悉并发编程。\n"
        "2. 熟悉 Kafka / Flink / Spark 等大数据组件。\n"
        "3. 有大规模分布式系统设计和落地经验。\n\n"
        "加分项：\n"
        "1. 熟悉大模型 / RAG 系统研发流程。\n"
        "2. 有 LangChain / LangGraph 使用经验。\n"
    )
    jd = LabeledJD(jd_id="jd_demo", jd_text=text, labels=_base_labels())
    chunks = split_jd(jd)

    assert len(chunks) == 3
    types = {c.chunk_type for c in chunks}
    assert types == {"responsibilities", "requirements", "perks"}

    first = chunks[0]
    assert first.source_id == "jd_demo"
    assert first.job_type == "tech"
    assert first.company == "字节跳动"


def test_split_jd_fallback_full() -> None:
    text = "我们招一个小伙伴，要求积极、有责任心、拥抱变化。"
    jd = LabeledJD(jd_id="jd_short", jd_text=text, labels=_base_labels())
    chunks = split_jd(jd)
    assert len(chunks) >= 1
    assert all(c.chunk_type == "full" for c in chunks)
    assert chunks[0].chunk_index == 0


# ---------------------------------------------------------------------------
# Interview splitter
# ---------------------------------------------------------------------------


def test_split_interview_per_turn_with_context() -> None:
    interview = StructuredInterview(
        interview_id="int_demo",
        company="字节跳动",
        position="算法工程师",
        level="senior",
        year=2024,
        outcome="offer",
        turns=[
            InterviewTurn(turn_id=1, role="interviewer", content="先自我介绍。", stage="intro"),
            InterviewTurn(turn_id=2, role="candidate", content="我做过 NLP。", stage="intro"),
            InterviewTurn(turn_id=3, role="interviewer", content="Transformer 原理？", stage="tech_qa"),
        ],
    )
    chunks = split_interview(interview)

    assert len(chunks) == 3
    assert chunks[0].doc_id == "int-int_demo-1"
    assert chunks[0].prev_turn_text == ""
    assert chunks[0].next_turn_text == "我做过 NLP。"
    assert chunks[1].prev_turn_text == "先自我介绍。"
    assert chunks[1].next_turn_text == "Transformer 原理？"
    assert chunks[2].next_turn_text == ""
    assert chunks[2].stage == "tech_qa"


# ---------------------------------------------------------------------------
# User splitter
# ---------------------------------------------------------------------------


def test_split_user_doc_canonical_sections(tmp_path: Path) -> None:
    md = (
        "# 张三\n\n"
        "## 基本信息\n姓名：张三\n\n"
        "## 教育经历\n### 北京大学\n本科\n\n"
        "## 项目经验\n### JobPilot\n做了 RAG 系统\n"
        "### 其他项目\n占位\n"
        "## 技能\nPython、Go\n"
    )
    p = tmp_path / "u_test_resume.md"
    p.write_text(md, encoding="utf-8")

    chunks = split_user_doc(p, user_id="u_test")
    assert chunks, "应当至少有一个 chunk"

    sections = {c.section for c in chunks}
    assert {"basic", "education", "projects", "skills"}.issubset(sections)

    jobpilot = [c for c in chunks if "JobPilot" in c.section_title]
    assert jobpilot, "section_title 必须命中 JobPilot"
    assert jobpilot[0].user_id == "u_test"
    assert jobpilot[0].doc_type == "resume"
