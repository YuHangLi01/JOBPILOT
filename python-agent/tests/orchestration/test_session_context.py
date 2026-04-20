"""SessionContextStore 单元测试（使用 fakeredis 避免真实 Redis 依赖）。"""

from __future__ import annotations

import json
import uuid

import pytest

from jobpilot_agent.orchestration.session_context import SessionContextStore


@pytest.fixture
async def store():
    """使用 fakeredis 的内存 store。"""
    fakeredis = pytest.importorskip("fakeredis.aioredis")
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    s = SessionContextStore.__new__(SessionContextStore)
    s._redis = fake_redis
    return s


async def test_save_and_load(store):
    chat_id = f"test_{uuid.uuid4().hex[:8]}"
    ctx = {"jd_summary": "高级前端 @ 字节跳动", "parsed_jd": {"company": "字节跳动"}}

    await store.save(chat_id, ctx)
    loaded = await store.load(chat_id)

    assert loaded is not None
    assert loaded["jd_summary"] == ctx["jd_summary"]
    assert loaded["parsed_jd"]["company"] == "字节跳动"


async def test_load_returns_none_for_missing_key(store):
    result = await store.load("nonexistent_chat_id")
    assert result is None


async def test_clear_removes_key(store):
    chat_id = f"test_{uuid.uuid4().hex[:8]}"
    await store.save(chat_id, {"x": 1})

    await store.clear(chat_id)
    result = await store.load(chat_id)
    assert result is None


async def test_save_overwrites_existing(store):
    chat_id = f"test_{uuid.uuid4().hex[:8]}"
    await store.save(chat_id, {"version": 1})
    await store.save(chat_id, {"version": 2})

    loaded = await store.load(chat_id)
    assert loaded["version"] == 2


async def test_key_format(store):
    """确认 key 格式为 session_context:{chat_id}。"""
    chat_id = "my_chat"
    assert store._key(chat_id) == "session_context:my_chat"
