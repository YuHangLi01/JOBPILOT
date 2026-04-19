"""命令行 demo：通过 HTTP API 与面试 Bot 进行一次完整模拟面试。

用法（先启动 FastAPI 服务）：
    uv run uvicorn jobpilot_agent.main:app --port 8001 --reload
    uv run python scripts/demo_interview.py
"""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx

BASE_URL = "http://localhost:8001"


async def main() -> None:
    thread_id = f"demo_{uuid.uuid4().hex[:8]}"
    company = input("公司（留空默认字节跳动）：").strip() or "字节跳动"
    position = input("岗位（留空默认高级后端工程师）：").strip() or "高级后端工程师"

    print(f"\n[面试开始] thread_id={thread_id}  {company} · {position}\n")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
        # 启动面试
        resp = await client.post(
            "/api/v1/agent/interview/start",
            json={
                "thread_id": thread_id,
                "user_id": "demo_user",
                "company": company,
                "position": position,
                "context": {},
            },
        )
        resp.raise_for_status()
        data = resp.json()

        round_num = 0
        while data["state"] == "waiting_user_input":
            action = data.get("next_action", {})
            stage = action.get("stage", "?")
            question = action.get("content", "（无问题）")

            print(f"\n【{stage}】面试官：{question}")
            user_input = input("你：").strip()
            if not user_input:
                user_input = "（无回答）"

            resp = await client.post(
                "/api/v1/agent/interview/resume",
                json={"thread_id": thread_id, "user_input": user_input},
            )
            resp.raise_for_status()
            data = resp.json()
            round_num += 1

            if round_num >= 40:
                print("\n[保护退出] 超过 40 轮，强制终止。")
                break

    print("\n=== 面试结束 ===")
    if data.get("report"):
        print(json.dumps(data["report"], indent=2, ensure_ascii=False))
    else:
        print("（未生成报告）")


if __name__ == "__main__":
    asyncio.run(main())
