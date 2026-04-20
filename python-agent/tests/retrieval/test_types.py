"""测试 retrieval/types.py 中的 Pydantic 数据模型。"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from jobpilot_agent.retrieval.types import (
    CollectionName,
    Document,
    RetrievalResult,
    SearchOptions,
)


# ---------------------------------------------------------------------------
# CollectionName
# ---------------------------------------------------------------------------


def test_collection_name_values() -> None:
    assert CollectionName.JD_KB.value == "jd_kb"
    assert CollectionName.INTERVIEW_KB.value == "interview_kb"
    assert CollectionName.USER_KB.value == "user_kb"


def test_collection_name_from_string() -> None:
    assert CollectionName("jd_kb") == CollectionName.JD_KB
    assert CollectionName("interview_kb") == CollectionName.INTERVIEW_KB


def test_collection_name_invalid() -> None:
    with pytest.raises(ValueError):
        CollectionName("not_exist")


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


def test_document_basic() -> None:
    doc = Document(
        doc_id="jd_kb-jd_001-0",
        collection=CollectionName.JD_KB,
        text="需要 3 年 Python 开发经验",
    )
    assert doc.doc_id == "jd_kb-jd_001-0"
    assert doc.collection == CollectionName.JD_KB
    assert doc.text == "需要 3 年 Python 开发经验"
    assert doc.metadata == {}
    assert isinstance(doc.created_at, datetime)


def test_document_with_metadata() -> None:
    doc = Document(
        doc_id="int_kb-int_001-0",
        collection=CollectionName.INTERVIEW_KB,
        text="字节跳动后端面经",
        metadata={"company": "字节跳动", "stage": "tech_qa", "chunk_index": 0},
    )
    assert doc.metadata["company"] == "字节跳动"
    assert doc.metadata["stage"] == "tech_qa"


def test_document_missing_required_field() -> None:
    with pytest.raises(ValidationError):
        Document(  # type: ignore[call-arg]
            doc_id="test",
            collection=CollectionName.JD_KB,
            # text 缺失
        )


def test_document_collection_from_string() -> None:
    doc = Document(
        doc_id="user_kb-u001-0",
        collection="user_kb",  # type: ignore[arg-type]
        text="简历内容",
    )
    assert doc.collection == CollectionName.USER_KB


# ---------------------------------------------------------------------------
# RetrievalResult
# ---------------------------------------------------------------------------


def test_retrieval_result_basic() -> None:
    r = RetrievalResult(
        doc_id="jd_kb-001-0",
        text="Python 高级工程师",
        metadata={"company": "字节跳动"},
        score=0.85,
    )
    assert r.score == 0.85
    assert r.dense_score is None
    assert r.sparse_score is None
    assert r.rerank_score is None
    assert r.rank_in_dense is None
    assert r.rank_in_sparse is None


def test_retrieval_result_full() -> None:
    r = RetrievalResult(
        doc_id="id-1",
        text="text",
        metadata={},
        score=0.6,
        dense_score=0.9,
        sparse_score=1.5,
        rerank_score=0.95,
        rank_in_dense=2,
        rank_in_sparse=1,
    )
    assert r.dense_score == 0.9
    assert r.sparse_score == 1.5
    assert r.rerank_score == 0.95
    assert r.rank_in_dense == 2
    assert r.rank_in_sparse == 1


def test_retrieval_result_score_zero() -> None:
    r = RetrievalResult(doc_id="x", text="t", metadata={}, score=0.0)
    assert r.score == 0.0


# ---------------------------------------------------------------------------
# SearchOptions
# ---------------------------------------------------------------------------


def test_search_options_defaults() -> None:
    opts = SearchOptions()
    assert opts.top_k == 5
    assert opts.filters is None
    assert opts.dense_weight is None
    assert opts.sparse_weight is None
    assert opts.dense_top_k == 20
    assert opts.sparse_top_k == 20
    assert opts.enable_rerank is False
    assert opts.rerank_top_k == 10


def test_search_options_custom() -> None:
    opts = SearchOptions(
        top_k=3,
        filters={"company": "字节跳动"},
        dense_weight=0.7,
        sparse_weight=0.3,
        enable_rerank=True,
        rerank_top_k=8,
    )
    assert opts.top_k == 3
    assert opts.filters == {"company": "字节跳动"}
    assert opts.dense_weight == 0.7
    assert opts.enable_rerank is True


def test_search_options_filters_none() -> None:
    opts = SearchOptions(top_k=10)
    assert opts.filters is None
