"""Session Context Store — 主图跑完后缓存结果，供面试子图启动时读取。

Key 格式：session_context:{feishu_chat_id}
TTL：24 小时（覆盖「今天分析 → 今天面试」场景）

设计约束：
- Redis 调用仅在 API 层发生，graph 节点保持纯净
- 若 Redis 不可达，降级为警告日志 + 返回 None（不崩溃）
- 使用全局单例，避免重复建连
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import redis.asyncio as aioredis

log = logging.getLogger(__name__)

_KEY_PREFIX = "session_context"
_TTL = timedelta(hours=24)

_store_singleton: Optional["SessionContextStore"] = None


class SessionContextStore:
    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis  # noqa: PLC0415

        self._redis: aioredis.Redis = aioredis.from_url(  # type: ignore[assignment]
            redis_url, decode_responses=True
        )

    def _key(self, chat_id: str) -> str:
        return f"{_KEY_PREFIX}:{chat_id}"

    async def save(self, chat_id: str, context: dict) -> None:
        try:
            await self._redis.setex(
                self._key(chat_id),
                int(_TTL.total_seconds()),
                json.dumps(context, ensure_ascii=False),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("session_context.save.failed", extra={"error": str(exc)})

    async def load(self, chat_id: str) -> Optional[dict]:
        try:
            data = await self._redis.get(self._key(chat_id))
            return json.loads(data) if data else None
        except Exception as exc:  # noqa: BLE001
            log.warning("session_context.load.failed", extra={"error": str(exc)})
            return None

    async def clear(self, chat_id: str) -> None:
        try:
            await self._redis.delete(self._key(chat_id))
        except Exception as exc:  # noqa: BLE001
            log.warning("session_context.clear.failed", extra={"error": str(exc)})

    async def ping(self) -> bool:
        try:
            await self._redis.ping()
            return True
        except Exception:  # noqa: BLE001
            return False

    async def close(self) -> None:
        try:
            await self._redis.aclose()
        except Exception:  # noqa: BLE001
            pass


def get_session_store() -> SessionContextStore:
    global _store_singleton
    if _store_singleton is None:
        from jobpilot_agent.config import get_settings  # noqa: PLC0415

        _store_singleton = SessionContextStore(get_settings().redis_url)
    return _store_singleton
