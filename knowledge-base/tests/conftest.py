"""pytest fixtures for kb_builder tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _set_minimal_env() -> None:
    """在测试进程中填充 jobpilot_agent.Settings 的必填项。"""
    os.environ.setdefault("LLM_API_KEY", "test-placeholder")
    os.environ.setdefault("RETRIEVAL_FALLBACK_TO_CHROMA", "true")


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def kb_root(repo_root: Path) -> Path:
    return repo_root / "knowledge-base"
