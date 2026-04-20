#!/usr/bin/env python
"""演示 JD 路由图的流式执行，打印每个节点的输出与耗时。

用法：
    cd python-agent
    uv run python scripts/demo_jd_routing.py
    uv run python scripts/demo_jd_routing.py --jd "后端工程师，要求 5 年 Python 经验..."
    uv run python scripts/demo_jd_routing.py --jd-file path/to/jd.txt

前置条件：
    - 设置 OPENAI_API_KEY（或 .env 文件）
    - 可选：GITHUB_TOKEN 以提升 GitHub API 速率限制
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# 确保 src/ 在 Python path 中
_src = Path(__file__).resolve().parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

DEMO_JD = """\
【职位】后端工程师（资深）
【公司】某互联网科技公司
【地点】北京

职位描述：
负责核心业务系统的设计与研发，参与分布式架构的演进与优化。

任职要求：
- 5年以上后端开发经验，精通 Python 或 Go
- 熟悉微服务架构、消息队列（Kafka/RabbitMQ）
- 有高并发、高可用系统设计经验
- 熟悉 LangChain / LangGraph 等 AI 框架者优先
- 良好的技术文档编写能力

薪资：25k-45k，18薪
"""


def _print_node_output(node_name: str, data: dict, elapsed_ms: int) -> None:
    """格式化打印单个节点的输出。"""
    print(f"\n{'=' * 60}")
    print(f"[节点] {node_name}  ({elapsed_ms}ms)")
    print(f"{'=' * 60}")

    # 只打印关键字段，避免输出过长
    display_keys = {
        "parse_jd": ["parsed_jd"],
        "classify_jd": ["classification"],
        "dispatch_skills": ["invoked_skills", "skipped_skills"],
        "invoke_skills_parallel": ["skill_outputs"],
        "merge_outputs": ["merged_skill_data"],
        "final_synthesis": ["final_result"],
    }

    keys_to_show = display_keys.get(node_name, list(data.keys()))
    for key in keys_to_show:
        if key in data:
            val = data[key]
            if isinstance(val, (dict, list)):
                serialized = json.dumps(val, ensure_ascii=False, indent=2)
                if len(serialized) > 800:
                    serialized = serialized[:800] + "\n  ... (truncated)"
                print(f"\n  {key}:\n{serialized}")
            else:
                print(f"\n  {key}: {val}")


async def run_demo(jd_text: str) -> None:
    """以流式方式运行 JD 路由图，逐节点打印输出。"""
    from jobpilot_agent.graphs.jd_routing_graph import get_jd_routing_graph

    print("\n[demo_jd_routing] 开始执行 JD 路由图...")
    print(f"JD 长度：{len(jd_text)} 字符\n")

    graph = get_jd_routing_graph()
    initial_state = {
        "request_id": "demo-001",
        "user_id": "demo-user",
        "jd_text": jd_text,
        "user_context": {"preferred_lang": "zh"},
        "skill_outputs": [],
        "metadata": {},
        "errors": [],
    }

    overall_start = time.monotonic()
    node_start = time.monotonic()

    async for event in graph.astream(initial_state, stream_mode="updates"):
        elapsed = int((time.monotonic() - node_start) * 1000)
        for node_name, node_data in event.items():
            _print_node_output(node_name, node_data, elapsed)
            node_start = time.monotonic()

    total_ms = int((time.monotonic() - overall_start) * 1000)
    print(f"\n{'=' * 60}")
    print(f"[完成] 总耗时：{total_ms}ms")
    print(f"{'=' * 60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="JD 路由图演示脚本")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--jd", type=str, help="直接传入 JD 文本")
    group.add_argument("--jd-file", type=str, help="从文件读取 JD 文本")
    args = parser.parse_args()

    if args.jd:
        jd_text = args.jd
    elif args.jd_file:
        jd_text = Path(args.jd_file).read_text(encoding="utf-8")
    else:
        jd_text = DEMO_JD
        print("[提示] 未指定 JD，使用内置演示 JD。可通过 --jd 或 --jd-file 指定。")

    asyncio.run(run_demo(jd_text))


if __name__ == "__main__":
    main()
