"""端到端 Demo：JD 路由 → 面试 → 报告

用法：
    cd python-agent
    uv run python scripts/demo_e2e.py

前提：
    - python-agent 运行在 http://localhost:8001
    - 已设置 PYTHON_AGENT_URL 或使用默认值
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import httpx

BASE_URL = "http://localhost:8001"

SAMPLE_JD = """
职位：高级前端工程师
公司：字节跳动
地点：北京

岗位职责：
- 负责抖音 Web 端核心功能研发
- 参与前端架构设计与技术选型
- 与产品、设计协同推进业务快速迭代

任职要求：
- 3 年以上前端开发经验
- 精通 React / TypeScript / Webpack 工具链
- 深入理解浏览器渲染机制与性能优化
- 有大型 SPA 项目架构经验者优先
"""


async def _run_interview_session(client: httpx.AsyncClient, chat_id: str) -> None:
    print("\n" + "=" * 60)
    print("Phase 2: Interview Session")
    print("=" * 60)

    r = await client.post(
        "/api/v1/agent/interview/start",
        json={"thread_id": chat_id, "user_id": "demo_user"},
        timeout=60,
    )
    if r.status_code != 200:
        print(f"[ERROR] /interview/start failed: {r.status_code} {r.text}")
        return

    data = r.json()

    while data.get("state") == "waiting_user_input":
        action = data.get("next_action") or {}
        stage = action.get("stage", "?")
        content = action.get("content", "")
        print(f"\n【{stage}】面试官：{content}")
        user_input = input("你：").strip()
        if not user_input:
            user_input = "（候选人暂时没有回答）"

        r = await client.post(
            "/api/v1/agent/interview/resume",
            json={"thread_id": chat_id, "user_input": user_input},
            timeout=60,
        )
        if r.status_code != 200:
            print(f"[ERROR] /interview/resume failed: {r.status_code} {r.text}")
            break
        data = r.json()

    if data.get("state") == "completed":
        print("\n" + "=" * 60)
        print("Phase 3: Interview Report")
        print("=" * 60)
        print(json.dumps(data.get("report"), indent=2, ensure_ascii=False))


async def main() -> None:
    chat_id = f"demo_{uuid.uuid4().hex[:8]}"

    print("=" * 60)
    print("Phase 1: JD Routing")
    print(f"Session ID: {chat_id}")
    print("=" * 60)

    jd_text = input("粘贴 JD 文本（或按 Enter 使用示例）：").strip() or SAMPLE_JD

    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        print("\n[分析中...]\n")
        r = await client.post(
            "/api/v1/agent/jd-routing",
            json={
                "request_id": str(uuid.uuid4()),
                "user_id": "demo_user",
                "jd_text": jd_text,
                "user_context": {
                    "feishu_chat_id": chat_id,
                    "preferred_lang": "zh",
                },
            },
            timeout=120,
        )

        if r.status_code != 200:
            print(f"[ERROR] JD routing failed: {r.status_code}\n{r.text}")
            sys.exit(1)

        data = r.json()

        cls = data.get("classification", {})
        print(f"[分类] job_type={cls.get('job_type')}  level={cls.get('level')}")
        print(f"[调用 Skills] {data.get('invoked_skills', [])}")
        print(f"\n[JD 摘要]\n{data['results']['jd_summary'][:300]}...")

        invitation = data["results"].get("interview_invitation")
        if invitation and invitation.get("should_invite"):
            print(f"\n✨  {invitation['cta_text']}")
            go = input("\n是否进入模拟面试？(y/N): ").strip().lower()
            if go == "y":
                await _run_interview_session(client, chat_id)
        else:
            print("\n（本次 JD 分析不符合面试邀请条件，仅展示分析结果）")

        print("\n[完整建议]")
        for item in data["results"].get("resume_advice", [])[:3]:
            print(f"  [{item['priority']}] {item['advice']}")


if __name__ == "__main__":
    asyncio.run(main())
