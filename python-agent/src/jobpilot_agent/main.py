"""
JobPilot Agent — FastAPI 应用入口
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from jobpilot_agent.api import health, interview, jd_routing, skills as skills_router
from jobpilot_agent.config import get_settings
from jobpilot_agent.logging_setup import (
    bind_request_context,
    clear_request_context,
    get_logger,
    setup_logging,
)

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    settings = get_settings()
    setup_logging(settings)
    log.info(
        "jobpilot_agent.startup",
        app_env=settings.app_env,
        port=settings.app_port,
    )
    from jobpilot_agent.graphs.interview.checkpointer import close_checkpointer, init_checkpointer
    from jobpilot_agent.skills.registry import register_all_skills

    register_all_skills()
    await init_checkpointer()

    # 预热 Redis 连接（不可达时仅警告，不阻止启动）
    from jobpilot_agent.orchestration.session_context import get_session_store  # noqa: PLC0415

    store = get_session_store()
    if await store.ping():
        log.info("redis.connected")
    else:
        log.warning("redis.unreachable", note="session_context will be unavailable")

    yield

    await close_checkpointer()
    await get_session_store().close()
    await _close_http_singletons()
    log.info("jobpilot_agent.shutdown")


async def _close_http_singletons() -> None:
    """关闭全局 HTTP 客户端单例，避免连接泄漏。

    每个单例独立 try/except，任一失败不影响其他清理。
    """
    # 飞书代理
    try:
        from jobpilot_agent.integrations.feishu_proxy import (  # noqa: PLC0415
            _singleton as _feishu_singleton,
        )

        if _feishu_singleton is not None:
            await _feishu_singleton.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("shutdown.feishu_proxy_close_failed", error=str(exc))

    # GitHub 客户端
    try:
        from jobpilot_agent.skills.github_scan.github_client import (  # noqa: PLC0415
            _singleton as _github_singleton,
        )

        if _github_singleton is not None:
            await _github_singleton.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("shutdown.github_client_close_failed", error=str(exc))

    # Embedder（若实现了 aclose，典型为 CachedEmbedder + DoubaoEmbedder）
    try:
        from jobpilot_agent.retrieval.embedding import get_embedder  # noqa: PLC0415

        embedder = get_embedder()
        close = getattr(embedder, "aclose", None)
        if callable(close):
            await close()
    except Exception as exc:  # noqa: BLE001
        log.warning("shutdown.embedder_close_failed", error=str(exc))


def _build_cors_origins() -> list[str]:
    settings = get_settings()
    # 允许 Node.js Gateway 的 callback origin
    from urllib.parse import urlparse

    parsed = urlparse(settings.nodejs_callback_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return [origin, "http://localhost:3000", "http://127.0.0.1:3000"]


app = FastAPI(
    title="JobPilot Agent",
    version="0.1.0",
    description="JobPilot AI Agent 服务层，提供 JD 路由分析与模拟面试功能。",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 请求上下文中间件 ───────────────────────────────────────────────────────────
@app.middleware("http")
async def request_context_middleware(request: Request, call_next: object) -> Response:
    # 优先取 X-Request-ID header，否则生成新 UUID
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    bind_request_context(request_id=request_id)

    start = time.monotonic()
    log.info(
        "http.request",
        method=request.method,
        path=request.url.path,
    )


    response: Response = await (call_next)(request)  # type: ignore[operator]

    elapsed_ms = int((time.monotonic() - start) * 1000)
    log.info(
        "http.response",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        latency_ms=elapsed_ms,
    )

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{elapsed_ms}ms"

    clear_request_context()
    return response


# ── 路由注册 ───────────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(jd_routing.router, prefix="/api/v1/agent")
app.include_router(interview.router, prefix="/api/v1/agent")
app.include_router(skills_router.router, prefix="/api/v1/skills")
