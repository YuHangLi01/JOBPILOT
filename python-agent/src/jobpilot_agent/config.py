from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── 服务配置 ──────────────────────────────────────────────
    app_env: Literal["dev", "staging", "prod"] = "dev"
    app_port: int = 8000
    log_level: str = "INFO"

    # ── 大模型（DeepSeek OpenAI 兼容接口） ───────────────────
    llm_api_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str  # required — 无默认值
    llm_model: str = "deepseek-chat"
    llm_model_lite: str = "deepseek-chat"

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
    embedding_cache_enabled: bool = True
    embedding_cache_size: int = 10000

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

    # ── Checkpointer（面试子图持久化） ─────────────────────────
    checkpointer_backend: Literal["postgres", "sqlite"] = "sqlite"
    sqlite_checkpoint_path: str = "./data/checkpoints.db"

    # ── Redis（Session Context 缓存） ─────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

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
