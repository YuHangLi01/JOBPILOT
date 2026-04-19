"""GitHub 公开 REST API 封装。

设计约束：
- 仅使用公开 API（无需 OAuth 大权限）
- token 可选（有 token 时 5000/h，无 token 时 60/h）
- 使用 httpx.AsyncClient 复用连接（通过单例工厂保证进程内复用）
- 不为每次请求新建客户端

反模式：
- 不从 JD 文本正则抽取 github 用户名（隐私风险）
- 不在此模块处理 Skill 逻辑（只负责 API 封装）
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from jobpilot_agent.config import get_settings
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

_GITHUB_API_BASE = "https://api.github.com"


class GitHubClient:
    """GitHub 公开 REST API v3 客户端。

    Example:
        >>> client = get_github_client()
        >>> user = await client.get_user("torvalds")
        >>> repos = await client.list_repos("torvalds", per_page=10)
    """

    def __init__(self, token: Optional[str] = None) -> None:
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        self._client = httpx.AsyncClient(
            base_url=_GITHUB_API_BASE,
            headers=headers,
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            follow_redirects=True,
        )
        self._has_token = bool(token)

    # ------------------------------------------------------------------
    # 用户信息
    # ------------------------------------------------------------------

    async def get_user(self, username: str) -> dict[str, Any]:
        """获取用户基本信息。

        Args:
            username: GitHub 用户名。

        Returns:
            GitHub 用户 JSON 数据（public_repos, followers 等）。

        Raises:
            httpx.HTTPStatusError: 404 用户不存在，或其他 HTTP 错误。
        """
        resp = await self._client.get(f"/users/{username}")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # 仓库列表
    # ------------------------------------------------------------------

    async def list_repos(
        self,
        username: str,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """列出用户的公开仓库，按最近更新时间排序。

        过滤规则：只返回非 fork 仓库（原创或 fork 但有 star）。

        Args:
            username: GitHub 用户名。
            per_page: 每页数量（最多 100）。

        Returns:
            仓库信息列表。
        """
        resp = await self._client.get(
            f"/users/{username}/repos",
            params={"sort": "updated", "per_page": min(per_page, 100), "type": "owner"},
        )
        resp.raise_for_status()
        repos: list[dict[str, Any]] = resp.json()

        # 过滤：排除纯 fork 且无 star 的水仓
        return [r for r in repos if not r.get("fork") or r.get("stargazers_count", 0) > 0]

    # ------------------------------------------------------------------
    # 语言分布
    # ------------------------------------------------------------------

    async def get_repo_languages(
        self, owner: str, repo: str
    ) -> dict[str, int]:
        """获取仓库各语言的代码行数。

        Args:
            owner: 仓库 owner（用户名或组织名）。
            repo: 仓库名。

        Returns:
            {语言名: 代码字节数} 字典，如 {"Python": 45321, "TypeScript": 12000}。
        """
        resp = await self._client.get(f"/repos/{owner}/{repo}/languages")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # README
    # ------------------------------------------------------------------

    async def get_readme(self, owner: str, repo: str) -> Optional[str]:
        """获取仓库 README 内容（解码为纯文本）。

        Args:
            owner: 仓库 owner。
            repo: 仓库名。

        Returns:
            README 文本内容，若不存在则返回 None。
        """
        try:
            resp = await self._client.get(f"/repos/{owner}/{repo}/readme")
            resp.raise_for_status()
            data = resp.json()
            content_b64: str = data.get("content", "")
            # GitHub 返回的是 base64 编码（含换行符）
            return base64.b64decode(content_b64.replace("\n", "")).decode("utf-8", errors="replace")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    # ------------------------------------------------------------------
    # 速率限制检查
    # ------------------------------------------------------------------

    async def get_rate_limit_remaining(self) -> int:
        """获取当前 API 速率限制剩余额度。

        Returns:
            剩余请求次数（-1 表示无法获取）。
        """
        try:
            resp = await self._client.get("/rate_limit")
            resp.raise_for_status()
            data = resp.json()
            return data.get("rate", {}).get("remaining", -1)
        except Exception:  # noqa: BLE001
            return -1

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def is_recent(repo: dict[str, Any], months: int = 6) -> bool:
        """判断仓库是否在近 N 个月内有 commit。

        Args:
            repo: 仓库 JSON 数据。
            months: 时间窗口（月数），默认 6。

        Returns:
            True 表示最近有活跃 commit。
        """
        pushed_at_str: Optional[str] = repo.get("pushed_at")
        if not pushed_at_str:
            return False
        try:
            pushed_at = datetime.fromisoformat(pushed_at_str.replace("Z", "+00:00"))
            cutoff = datetime.now(tz=timezone.utc) - timedelta(days=30 * months)
            return pushed_at >= cutoff
        except ValueError:
            return False

    async def close(self) -> None:
        """关闭底层 HTTP 连接池。"""
        await self._client.aclose()


# ---------------------------------------------------------------------------
# 进程级单例工厂
# ---------------------------------------------------------------------------

_singleton: Optional[GitHubClient] = None


def get_github_client() -> GitHubClient:
    """返回 GitHubClient 进程级单例（延迟初始化）。

    从 settings 读取 github_token（可为 None），自动应用认证头。

    Returns:
        GitHubClient 单例。
    """
    global _singleton
    if _singleton is None:
        token = get_settings().github_token
        _singleton = GitHubClient(token=token)
        log.info(
            "github_client.initialized",
            authenticated=bool(token),
            rate_limit="5000/h" if token else "60/h",
        )
    return _singleton


def reset_github_client_singleton() -> None:
    """重置单例，主要供测试使用。"""
    global _singleton
    _singleton = None
