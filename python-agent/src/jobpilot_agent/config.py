from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── 服务配置 ──────────────────────────────────────────────
    app_env: Literal["dev", "staging", "prod"] = "dev"
    app_port: int = 8000
    log_level: str = "INFO"

    # ── 大模型（火山方舟 OpenAI 兼容接口） ───────────────────
    llm_api_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    llm_api_key: str  # required — 无默认值
    llm_model: str = "doubao-pro-4k"
    llm_model_lite: str = "doubao-lite-4k"

    # ── 向量数据库 ────────────────────────────────────────────
    milvus_uri: str = "http://localhost:19530"

    # ── 关系数据库（LangGraph Checkpointer） ─────────────────
    postgres_url: str = ""

    # ── Node.js 内部回调 ──────────────────────────────────────
    nodejs_callback_url: str = "http://localhost:3000/internal"
    nodejs_internal_secret: str = ""

    # ── 嵌入模型 ─────────────────────────────────────────────
    embedding_provider: Literal["local", "doubao"] = "local"
    embedding_model_name: str = "BAAI/bge-m3"
    embedding_dimension: int = 1024

    # ── 精排器 ───────────────────────────────────────────────
    reranker_model_name: str = "BAAI/bge-reranker-v2-m3"
    reranker_enabled_default: bool = False

    # ── BM25 索引持久化 ──────────────────────────────────────
    bm25_index_dir: str = "./data/bm25_indexes"

    # ── Milvus 扩展配置 ──────────────────────────────────────
    milvus_db_name: str = "default"

    # ── 降级策略 ─────────────────────────────────────────────
    retrieval_fallback_to_chroma: bool = True
    chroma_persist_dir: str = "./data/chroma"

    # ── GitHub 集成 ───────────────────────────────────────────
    github_token: str | None = None
    github_rate_limit_buffer: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    """单例工厂；测试中可通过 get_settings.cache_clear() 重置。"""
    return Settings()
