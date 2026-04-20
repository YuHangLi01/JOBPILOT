"""
pytest 全局 fixture 配置

在所有测试开始前注入必要的环境变量，防止 Settings 因缺失 required 字段而报错。
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

# Load real .env first so os.environ.setdefault() below uses the real key as the base.
# Without this, subprocess tests inherit "test-dummy-key" and fail with 401.
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

# 必须在 import jobpilot_agent 之前注入，避免 Settings 实例化失败
os.environ.setdefault("LLM_API_KEY", "test-dummy-key")
os.environ.setdefault("POSTGRES_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("APP_ENV", "dev")


@pytest.fixture(scope="session")
def client() -> TestClient:
    """提供复用同一 app 实例的同步测试客户端。"""
    from jobpilot_agent.config import get_settings
    from jobpilot_agent.main import app

    # 清除 lru_cache，确保测试用环境变量生效
    get_settings.cache_clear()

    return TestClient(app, raise_server_exceptions=True)
