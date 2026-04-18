"""
飞书资源代理客户端

通过 Node.js Gateway 的 /internal/* 接口访问飞书资源，
避免 Python Agent 直接持有飞书凭证。
当前为 stub 实现，下周接入真实逻辑。
"""

from __future__ import annotations

from typing import Any

import httpx

from jobpilot_agent.config import get_settings
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


def _get_headers() -> dict[str, str]:
    settings = get_settings()
    return {"X-Internal-Secret": settings.nodejs_internal_secret}


async def read_feishu_doc(doc_token: str) -> dict[str, Any]:  # noqa: ARG001
    """读取飞书云文档（stub）。"""
    log.info("feishu_proxy.read_doc.stub", doc_token=doc_token)
    return {"ok": True, "data": None}


async def query_bitable(
    app_token: str,
    table_id: str,
    filter_expr: dict[str, Any] | None = None,
) -> dict[str, Any]:  # noqa: ARG001
    """查询飞书多维表格（stub）。"""
    log.info(
        "feishu_proxy.query_bitable.stub",
        app_token=app_token,
        table_id=table_id,
    )
    return {"ok": True, "data": None}


async def upload_file(filename: str, content: bytes) -> dict[str, Any]:  # noqa: ARG001
    """上传文件到飞书（stub）。"""
    log.info("feishu_proxy.upload_file.stub", filename=filename, size=len(content))
    return {"ok": True, "data": None}


class FeishuProxyClient:
    """
    有状态的代理客户端（复用 httpx.AsyncClient）。
    在需要复用连接池时使用；stub 模式下方法签名预留，实现为占位。
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.nodejs_callback_url
        self._headers = _get_headers()
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> FeishuProxyClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=10.0,
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client:
            await self._client.aclose()
