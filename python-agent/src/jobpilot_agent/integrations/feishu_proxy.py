"""飞书 API 代理客户端。

Python Agent 不直接调用飞书 API，而通过 Node.js Gateway 的内部接口代理。
这是双栈架构的核心约束：飞书 SDK 和凭证仅在 Node.js 侧维护。

调用链：
  Python FeishuProxyClient
    → POST {nodejs_callback_url}/feishu/docs/read
      → Node.js internal.routes.ts
        → FeishuDocumentService.readDocAsMarkdown()
          → 飞书 docx API

设计约束：
- 所有 HTTP 错误均以原始 httpx.HTTPError / httpx.TimeoutException 抛出
  调用方（Skill.invoke）负责捕获并转换为 SkillOutput(success=False)
- 不直接 import 任何飞书 SDK
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from jobpilot_agent.config import get_settings
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


class FeishuProxyClient:
    """通过 Node.js Gateway 代理调用飞书 API 的客户端。

    所有方法均为 async，内部使用 httpx.AsyncClient 复用连接。

    Example:
        >>> client = get_feishu_proxy()
        >>> md = await client.read_doc("my_doc_token")
        >>> print(md[:100])
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.nodejs_callback_url.rstrip("/")
        secret = settings.nodejs_internal_secret
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=20.0, write=5.0, pool=5.0),
            headers={
                "X-Internal-Secret": secret,
                "Content-Type": "application/json",
            },
        )

    async def read_doc(self, doc_token: str) -> str:
        """读取飞书云文档，返回 Markdown 格式内容。

        Args:
            doc_token: 飞书云文档的 token（document_id）。

        Returns:
            文档内容的 Markdown 字符串。

        Raises:
            httpx.HTTPStatusError: Node.js 返回 4xx/5xx。
            httpx.TimeoutException: 请求超时。
            ValueError: Node.js 返回 ok=false（飞书 API 错误）。
        """
        url = f"{self._base_url}/feishu/docs/read"
        log.debug("feishu_proxy.read_doc", url=url, doc_token=doc_token[:8] + "...")

        resp = await self._client.post(url, json={"doc_token": doc_token})
        resp.raise_for_status()

        data = resp.json()
        if not data.get("ok"):
            error_code = data.get("error_code", "UNKNOWN")
            error_msg = data.get("error_message", "unknown error")
            raise ValueError(f"Feishu API error [{error_code}]: {error_msg}")

        content: str = data["content"]
        log.debug(
            "feishu_proxy.read_doc.done",
            doc_token=doc_token[:8] + "...",
            content_len=len(content),
        )
        return content

    async def query_bitable(
        self,
        app_token: str,
        table_id: str,
        filter_condition: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """查询飞书多维表格记录。

        Args:
            app_token: 多维表格应用 token。
            table_id: 表格 ID。
            filter_condition: 过滤条件（与 Node.js 约定格式对齐）。

        Returns:
            记录列表（dict 格式）。

        Raises:
            httpx.HTTPStatusError: 请求失败。
            ValueError: 飞书 API 返回错误。
        """
        url = f"{self._base_url}/feishu/bitable/query"
        payload: dict[str, Any] = {"app_token": app_token, "table_id": table_id}
        if filter_condition:
            payload["filter"] = filter_condition

        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()

        data = resp.json()
        if not data.get("ok"):
            error_code = data.get("error_code", "UNKNOWN")
            error_msg = data.get("error_message", "unknown error")
            raise ValueError(f"Feishu Bitable error [{error_code}]: {error_msg}")

        return data.get("records", [])

    async def close(self) -> None:
        """关闭底层 HTTP 连接池。在测试或应用关闭时调用。"""
        await self._client.aclose()


# ---------------------------------------------------------------------------
# 进程级单例
# ---------------------------------------------------------------------------

_singleton: Optional[FeishuProxyClient] = None


def get_feishu_proxy() -> FeishuProxyClient:
    """返回 FeishuProxyClient 进程级单例。

    延迟初始化，首次调用时创建，之后复用同一实例（复用 httpx 连接池）。

    Returns:
        FeishuProxyClient 单例。
    """
    global _singleton
    if _singleton is None:
        _singleton = FeishuProxyClient()
        log.info("feishu_proxy.initialized")
    return _singleton


def reset_feishu_proxy_singleton() -> None:
    """重置单例，主要供测试使用。"""
    global _singleton
    _singleton = None
