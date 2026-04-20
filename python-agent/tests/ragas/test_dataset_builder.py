"""dataset_builder 单元测试（不依赖外部服务）。"""

from __future__ import annotations

import random

import pytest

from jobpilot_agent.evaluation.ragas.dataset_builder import (
    _build_question,
    _extract_company_position,
    _stratified_sample,
)
from jobpilot_agent.evaluation.ragas.schema import RagasExample


# ── _extract_company_position ─────────────────────────────────────────────────


def test_extract_company_from_jd_text():
    jd = "公司：字节跳动\n岗位职责：...\n任职资格：..."
    company, _ = _extract_company_position(jd, {})
    assert company == "字节跳动"


def test_extract_position_from_jd_text():
    jd = "职位名称：高级前端工程师\n岗位职责：..."
    _, position = _extract_company_position(jd, {"sub_type": "frontend"})
    assert "高级前端" in position or "frontend" in position


def test_fallback_to_labels_sub_type_when_no_regex_match():
    jd = "这是一段没有标准格式的 JD 文本"
    _, position = _extract_company_position(jd, {"sub_type": "backend"})
    assert position == "backend"


def test_company_fallback_to_default():
    jd = "这是一段没有公司名的文本"
    company, _ = _extract_company_position(jd, {})
    assert company == "目标公司"


# ── _build_question ───────────────────────────────────────────────────────────


def test_build_question_contains_company_and_position():
    q = _build_question("字节跳动", "高级前端工程师")
    assert "字节跳动" in q
    assert "高级前端工程师" in q


def test_build_question_asks_for_interview_questions():
    q = _build_question("A公司", "B岗位")
    assert "面试" in q or "问题" in q


# ── _stratified_sample ────────────────────────────────────────────────────────


def _make_items(job_types: list[str]) -> list[dict]:
    return [{"job_type": jt, "id": i} for i, jt in enumerate(job_types)]


def test_stratified_sample_returns_correct_size():
    items = _make_items(["tech"] * 80 + ["product"] * 20)
    rng = random.Random(42)
    result = _stratified_sample(items, 10, lambda x: x["job_type"], rng)
    assert len(result) <= 10


def test_stratified_sample_preserves_proportions():
    items = _make_items(["tech"] * 80 + ["product"] * 20)
    rng = random.Random(42)
    result = _stratified_sample(items, 100, lambda x: x["job_type"], rng)
    tech_count = sum(1 for x in result if x["job_type"] == "tech")
    product_count = sum(1 for x in result if x["job_type"] == "product")
    # tech 应多于 product
    assert tech_count > product_count


def test_stratified_sample_handles_pool_smaller_than_size():
    items = _make_items(["tech"] * 5)
    rng = random.Random(42)
    result = _stratified_sample(items, 10, lambda x: x["job_type"], rng)
    # 不应超过 pool 大小
    assert len(result) <= len(items)


def test_stratified_sample_deterministic():
    items = _make_items(["tech"] * 50 + ["ops"] * 50)
    r1 = _stratified_sample(items, 20, lambda x: x["job_type"], random.Random(42))
    r2 = _stratified_sample(items, 20, lambda x: x["job_type"], random.Random(42))
    assert [x["id"] for x in r1] == [x["id"] for x in r2]
