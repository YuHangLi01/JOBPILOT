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

from jobpilot_agent.api import health, interview, jd_routing
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
    yield
    log.info("jobpilot_agent.shutdown")


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
