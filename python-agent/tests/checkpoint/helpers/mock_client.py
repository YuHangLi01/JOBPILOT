"""模拟面试用户客户端。"""

from __future__ import annotations

from collections.abc import Callable

import httpx

_BASE = "/api/v1/agent"


class InterviewMockClient:
    """以 httpx 包装面试 API，用于自动化测试。"""

    def __init__(self, base_url: str, thread_id: str) -> None:
        self.base_url = base_url
        self.thread_id = thread_id
        self._client = httpx.AsyncClient(base_url=base_url, timeout=120.0)

    async def start(
        self,
        company: str,
        position: str,
        user_id: str = "test_user",
    ) -> dict[str, object]:
        r = await self._client.post(
            f"{_BASE}/interview/start",
            json={
                "thread_id": self.thread_id,
                "user_id": user_id,
                "company": company,
                "position": position,
                "context": {},
            },
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    async def resume(self, user_input: str) -> dict[str, object]:
        r = await self._client.post(
            f"{_BASE}/interview/resume",
            json={
                "thread_id": self.thread_id,
                "user_input": user_input,
            },
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    async def status(self) -> dict[str, object]:
        r = await self._client.get(
            f"{_BASE}/interview/{self.thread_id}/status"
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    async def get_full_state(self) -> dict[str, object]:
        r = await self._client.get(
            f"{_BASE}/interview/{self.thread_id}/_debug_state"
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    async def close(self) -> None:
        await self._client.aclose()


async def run_n_rounds(
    client: InterviewMockClient,
    current_data: dict[str, object],
    n_rounds: int,
    answer_generator: Callable[[str], str] | None = None,
) -> dict[str, object]:
    """从 current_data 出发，持续 resume 直到完成或达到 n_rounds 轮。

    current_data 是最近一次 API 响应 dict（含 state / next_action）。
    answer_generator 接收 stage 字符串，返回候选人回答文本。
    """
    if answer_generator is None:
        answer_generator = lambda stage: (  # noqa: E731
            f"这是针对 {stage} 阶段的模拟回答。"
            "我在项目中使用了分布式缓存和微服务架构，遇到了性能瓶颈并通过水平扩展解决。"
        )

    data = current_data
    rounds = 0
    while data.get("state") == "waiting_user_input" and rounds < n_rounds:
        next_action = data.get("next_action") or {}
        stage = str((next_action or {}).get("stage", "intro"))  # type: ignore[union-attr]
        answer = answer_generator(stage)
        data = await client.resume(answer)
        rounds += 1
    return data
