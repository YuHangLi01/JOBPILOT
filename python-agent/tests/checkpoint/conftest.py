"""pytest fixtures for checkpoint tests."""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture
def sqlite_path():
    """提供一个临时 SQLite 文件路径；同一测试内的 kill/restart 共用同一文件。"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


@pytest.fixture
def postgres_url() -> str | None:
    """从环境变量读取 Postgres 测试 URL。"""
    return os.getenv("POSTGRES_TEST_URL")
