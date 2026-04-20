"""集成测试：MilvusVectorStore。

需要本地 Milvus Standalone 运行在 localhost:19530。

运行方式：
    pytest tests/retrieval/test_milvus_vector_store.py -m integration -v

跳过（默认）：
    pytest tests/retrieval/  # 不带 -m integration 时自动跳过
"""

import time
import uuid

import numpy as np
import pytest

from jobpilot_agent.retrieval.types import CollectionName, Document

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def milvus_store():  # type: ignore[return]
    """模块级 Milvus 连接，所有 test 共享同一个客户端。"""
    from jobpilot_agent.retrieval.vector_store import MilvusVectorStore

    store = MilvusVectorStore(uri="http://localhost:19530")
    yield store


@pytest.fixture
def tmp_collection(milvus_store) -> CollectionName:  # type: ignore[return]
    """每个 test 使用独立的 CollectionName（通过动态枚举扩展）。

    由于 CollectionName 是枚举，我们用固定的 JD_KB 集合但加时间戳后缀的方式：
    实际创建临时集合并在 test 结束后删除。
    """
    # 为避免修改枚举，直接在 Milvus 侧用带随机后缀的字符串名
    # 这里简单用 JD_KB 并在每次测试前 drop + recreate
    col = CollectionName.JD_KB
    # 先 drop 清理
    try:
        milvus_store.drop(col)
    except Exception:
        pass
    milvus_store.create_collection(col, dimension=4)  # 用 dim=4 的小向量加速测试
    yield col
    try:
        milvus_store.drop(col)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 帮助函数
# ---------------------------------------------------------------------------


def small_embedding(n: int, dim: int = 4) -> np.ndarray:
    """生成随机 L2 归一化向量。"""
    vecs = np.random.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / norms


def make_doc(i: int, company: str = "字节跳动") -> Document:
    return Document(
        doc_id=f"jd_kb-test_{i:03d}-0",
        collection=CollectionName.JD_KB,
        text=f"文档 {i} Python 后端工程师 {company}",
        metadata={"company": company, "source_id": f"test_{i:03d}", "chunk_index": 0},
    )


# ---------------------------------------------------------------------------
# 基础 CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_collection_idempotent(milvus_store) -> None:
    """重复创建 collection 不应报错。"""
    col = CollectionName.INTERVIEW_KB
    try:
        milvus_store.drop(col)
    except Exception:
        pass
    milvus_store.create_collection(col, dimension=4)
    milvus_store.create_collection(col, dimension=4)  # 第二次应幂等
    milvus_store.drop(col)


@pytest.mark.asyncio
async def test_upsert_and_count(milvus_store, tmp_collection) -> None:
    docs = [make_doc(i) for i in range(5)]
    embeddings = small_embedding(5, dim=4)
    await milvus_store.upsert(tmp_collection, docs, embeddings)

    time.sleep(0.5)  # Milvus 异步刷新
    count = milvus_store.count(tmp_collection)
    assert count == 5


@pytest.mark.asyncio
async def test_upsert_overwrites_same_doc_id(milvus_store, tmp_collection) -> None:
    doc = make_doc(1)
    emb = small_embedding(1, dim=4)
    await milvus_store.upsert(tmp_collection, [doc], emb)
    await milvus_store.upsert(tmp_collection, [doc], emb)  # 覆盖

    time.sleep(0.5)
    count = milvus_store.count(tmp_collection)
    assert count == 1


# ---------------------------------------------------------------------------
# 搜索
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_top_k(milvus_store, tmp_collection) -> None:
    docs = [make_doc(i) for i in range(5)]
    embeddings = small_embedding(5, dim=4)
    await milvus_store.upsert(tmp_collection, docs, embeddings)
    time.sleep(0.5)

    query_vec = small_embedding(1, dim=4)[0]
    results = await milvus_store.search(tmp_collection, query_vec, top_k=3)
    assert len(results) <= 3
    assert len(results) > 0


@pytest.mark.asyncio
async def test_search_dense_score_filled(milvus_store, tmp_collection) -> None:
    docs = [make_doc(1)]
    emb = small_embedding(1, dim=4)
    await milvus_store.upsert(tmp_collection, docs, emb)
    time.sleep(0.5)

    query_vec = small_embedding(1, dim=4)[0]
    results = await milvus_store.search(tmp_collection, query_vec, top_k=1)
    if results:
        assert results[0].dense_score is not None
        assert results[0].rank_in_dense == 1


@pytest.mark.asyncio
async def test_search_empty_collection_returns_empty(milvus_store, tmp_collection) -> None:
    query_vec = small_embedding(1, dim=4)[0]
    # 集合刚创建，无数据
    results = await milvus_store.search(tmp_collection, query_vec, top_k=5)
    assert results == []


# ---------------------------------------------------------------------------
# 集合管理
# ---------------------------------------------------------------------------


def test_list_collections_includes_created(milvus_store, tmp_collection) -> None:
    cols = milvus_store.list_collections()
    assert CollectionName.JD_KB.value in cols


def test_drop_collection(milvus_store) -> None:
    col = CollectionName.USER_KB
    milvus_store.create_collection(col, dimension=4)
    milvus_store.drop(col)
    cols = milvus_store.list_collections()
    assert CollectionName.USER_KB.value not in cols


# ---------------------------------------------------------------------------
# 动态字段回传（P2.3 依赖）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_returns_dynamic_fields(milvus_store, tmp_collection) -> None:
    """search() 必须把入库时写入的动态字段（如 job_type/stage）原样回传到 metadata。"""
    doc = Document(
        doc_id="jd_kb-dynfield-0",
        collection=CollectionName.JD_KB,
        text="高级前端工程师 React TypeScript",
        metadata={
            "source_id": "dynfield",
            "chunk_index": 0,
            "company": "字节跳动",
            "position": "前端",
            # 以下都是动态字段
            "job_type": "tech",
            "sub_type": "frontend",
            "level": "senior",
            "chunk_type": "requirements",
        },
    )
    emb = small_embedding(1, dim=4)
    await milvus_store.upsert(tmp_collection, [doc], emb)
    time.sleep(0.5)

    query_vec = small_embedding(1, dim=4)[0]
    results = await milvus_store.search(tmp_collection, query_vec, top_k=1)
    assert results, "期望至少返回一条结果"
    md = results[0].metadata
    assert md.get("job_type") == "tech"
    assert md.get("sub_type") == "frontend"
    assert md.get("level") == "senior"
    assert md.get("chunk_type") == "requirements"
