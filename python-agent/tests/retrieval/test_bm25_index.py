"""测试 retrieval/bm25.py — BM25Index 功能。"""

import os
import pickle
import tempfile

import pytest

from jobpilot_agent.retrieval.bm25 import BM25Index, _match_filters
from jobpilot_agent.retrieval.types import CollectionName, Document


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_doc(i: int, company: str = "默认公司", text: str = "") -> Document:
    return Document(
        doc_id=f"jd_kb-jd_{i:03d}-0",
        collection=CollectionName.JD_KB,
        text=text or f"岗位{i}：Python 后端工程师，需要{i}年工作经验，熟悉 Docker 和 Kubernetes",
        metadata={"company": company, "source_id": f"jd_{i:03d}", "chunk_index": 0},
    )


@pytest.fixture
def index_with_10_docs() -> BM25Index:
    docs = [
        make_doc(1, "字节跳动", "Python 后端工程师，3年经验，熟悉 Docker"),
        make_doc(2, "字节跳动", "前端工程师 React TypeScript，2年经验"),
        make_doc(3, "阿里巴巴", "Java 架构师，5年以上，分布式系统"),
        make_doc(4, "阿里巴巴", "机器学习工程师，PyTorch，NLP 方向"),
        make_doc(5, "腾讯", "Go 后端工程师，Kubernetes 运维经验"),
        make_doc(6, "腾讯", "产品经理，用户研究，数据分析"),
        make_doc(7, "百度", "算法工程师，Python，RAG 检索增强"),
        make_doc(8, "百度", "数据工程师，Spark，数仓建设"),
        make_doc(9, "美团", "Python 工程师，微服务架构，Redis"),
        make_doc(10, "美团", "Android 移动端工程师，Kotlin"),
    ]
    idx = BM25Index(CollectionName.JD_KB)
    idx.build(docs)
    return idx


# ---------------------------------------------------------------------------
# build & 空索引保护
# ---------------------------------------------------------------------------


def test_build_empty_does_not_raise() -> None:
    idx = BM25Index(CollectionName.JD_KB)
    idx.build([])  # 不应崩溃
    assert len(idx) == 0


def test_build_sets_length(index_with_10_docs: BM25Index) -> None:
    assert len(index_with_10_docs) == 10


def test_search_empty_index_returns_empty() -> None:
    idx = BM25Index(CollectionName.JD_KB)
    idx.build([])
    results = idx.search("Python 后端")
    assert results == []


def test_search_on_unbuilt_index_returns_empty() -> None:
    idx = BM25Index(CollectionName.INTERVIEW_KB)
    results = idx.search("任何查询")
    assert results == []


# ---------------------------------------------------------------------------
# 基础检索
# ---------------------------------------------------------------------------


def test_search_returns_results(index_with_10_docs: BM25Index) -> None:
    results = index_with_10_docs.search("Python 后端", top_k=3)
    assert len(results) <= 3
    assert len(results) > 0


def test_search_python_ranks_python_docs_higher(index_with_10_docs: BM25Index) -> None:
    results = index_with_10_docs.search("Python 后端工程师", top_k=5)
    doc_texts = [r.text for r in results]
    # 至少一条结果包含 Python
    assert any("Python" in t for t in doc_texts)


def test_search_scores_descending(index_with_10_docs: BM25Index) -> None:
    results = index_with_10_docs.search("Python 后端", top_k=10)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_search_fills_sparse_score(index_with_10_docs: BM25Index) -> None:
    results = index_with_10_docs.search("Python")
    for r in results:
        assert r.sparse_score is not None
        assert r.rank_in_sparse is not None


def test_search_rank_starts_at_one(index_with_10_docs: BM25Index) -> None:
    results = index_with_10_docs.search("Python", top_k=5)
    if results:
        assert results[0].rank_in_sparse == 1


def test_search_top_k_respected(index_with_10_docs: BM25Index) -> None:
    results = index_with_10_docs.search("工程师", top_k=2)
    assert len(results) <= 2


# ---------------------------------------------------------------------------
# 过滤器
# ---------------------------------------------------------------------------


def test_filter_by_company_exact(index_with_10_docs: BM25Index) -> None:
    results = index_with_10_docs.search("工程师", top_k=10, filters={"company": "字节跳动"})
    for r in results:
        assert "字节跳动" in r.metadata.get("company", "")


def test_filter_by_company_substring(index_with_10_docs: BM25Index) -> None:
    """字节 是 字节跳动 的子串，应能匹配。"""
    results = index_with_10_docs.search("工程师", top_k=10, filters={"company": "字节"})
    assert len(results) > 0
    for r in results:
        assert "字节" in r.metadata.get("company", "")


def test_filter_no_match_returns_empty(index_with_10_docs: BM25Index) -> None:
    results = index_with_10_docs.search("工程师", filters={"company": "不存在的公司XYZ"})
    assert results == []


def test_filter_nonexistent_key_returns_empty(index_with_10_docs: BM25Index) -> None:
    results = index_with_10_docs.search("Python", filters={"nonexistent_key": "value"})
    assert results == []


# ---------------------------------------------------------------------------
# 持久化：save / load
# ---------------------------------------------------------------------------


def test_save_and_load(index_with_10_docs: BM25Index) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "bm25_jd_kb.pkl")
        index_with_10_docs.save(path)

        loaded = BM25Index.load(path)
        assert len(loaded) == len(index_with_10_docs)
        assert loaded.collection == CollectionName.JD_KB

        # 加载后检索结果应与原索引一致
        r1 = index_with_10_docs.search("Python", top_k=3)
        r2 = loaded.search("Python", top_k=3)
        assert [r.doc_id for r in r1] == [r.doc_id for r in r2]


def test_load_file_not_found() -> None:
    with pytest.raises(FileNotFoundError):
        BM25Index.load("/nonexistent/path/bm25.pkl")


# ---------------------------------------------------------------------------
# add_or_update
# ---------------------------------------------------------------------------


def test_add_or_update_increases_size() -> None:
    idx = BM25Index(CollectionName.JD_KB)
    idx.build([make_doc(1)])
    assert len(idx) == 1
    idx.add_or_update([make_doc(2)])
    assert len(idx) == 2


def test_add_or_update_overwrites_same_doc_id() -> None:
    idx = BM25Index(CollectionName.JD_KB)
    doc1 = make_doc(1, text="原始文本内容")
    idx.build([doc1])
    doc1_updated = Document(
        doc_id=doc1.doc_id,
        collection=CollectionName.JD_KB,
        text="更新后的内容 Python Golang",
        metadata={},
    )
    idx.add_or_update([doc1_updated])
    assert len(idx) == 1  # 覆盖，不增加


# ---------------------------------------------------------------------------
# _match_filters 单元测试
# ---------------------------------------------------------------------------


def test_match_filters_exact() -> None:
    assert _match_filters({"company": "字节跳动"}, {"company": "字节跳动"}) is True


def test_match_filters_substring() -> None:
    assert _match_filters({"company": "字节跳动"}, {"company": "字节"}) is True


def test_match_filters_no_match() -> None:
    assert _match_filters({"company": "字节跳动"}, {"company": "阿里"}) is False


def test_match_filters_missing_key() -> None:
    assert _match_filters({"company": "字节"}, {"stage": "tech_qa"}) is False


def test_match_filters_empty_filters() -> None:
    assert _match_filters({"company": "字节"}, {}) is True


def test_match_filters_multiple_conditions() -> None:
    meta = {"company": "字节跳动", "stage": "tech_qa"}
    assert _match_filters(meta, {"company": "字节", "stage": "tech_qa"}) is True
    assert _match_filters(meta, {"company": "字节", "stage": "hr"}) is False
