#!/usr/bin/env python
"""场景 A 评估运行脚本。

用法：
    # 小样本验证（先跑通再跑全量）
    uv run python scripts/run_scenario_a_eval.py --mode main --sample 50 --output evaluation/runs/main_50.jsonl

    # 主图全量评估
    uv run python scripts/run_scenario_a_eval.py --mode main --sample 500

    # Baseline 全量评估
    uv run python scripts/run_scenario_a_eval.py --mode baseline --sample 500

    # 断点续跑（指定同一 output 文件，已完成的 jd_id 将被跳过）
    uv run python scripts/run_scenario_a_eval.py --mode main --sample 500 --output evaluation/runs/main_20260501.jsonl

运行时间估算：
    500 条 × ~10s/条 ÷ 5 并发 ≈ 1000s（约 17 分钟）
    建议用 tmux 防断联：tmux new-session -s eval
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

_src = Path(__file__).resolve().parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


def _default_output(mode: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    return f"evaluation/runs/{mode}_{ts}.jsonl"


async def main() -> None:
    parser = argparse.ArgumentParser(description="场景 A 评估主入口")
    parser.add_argument(
        "--mode",
        choices=["main", "baseline"],
        required=True,
        help="运行模式：main=主图（有路由），baseline=全选 Skill",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="抽样数量；不指定则全量（500 条）",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="结果输出 JSONL 路径（支持断点续跑）",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="LLM 并发数（默认 5，避免打爆 API）",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="knowledge-base/data/labeled/jd_labeled.jsonl",
        help="数据集路径",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=20,
        help="每处理多少条写一次磁盘（断点续跑间隔）",
    )
    args = parser.parse_args()

    output_path = args.output or _default_output(args.mode)
    print(f"[run_scenario_a_eval] mode={args.mode}, sample={args.sample}, output={output_path}")

    from jobpilot_agent.evaluation.datasets.loader import load_jd_eval_dataset
    from jobpilot_agent.evaluation.runners.scenario_a_runner import ScenarioARunner

    print("[1/3] 加载数据集...")
    dataset = load_jd_eval_dataset(path=args.dataset, sample_size=args.sample)
    print(f"      已加载 {len(dataset)} 条样本")

    print("[2/3] 初始化图...")
    if args.mode == "main":
        from jobpilot_agent.graphs.jd_routing_graph import get_jd_routing_graph
        graph = get_jd_routing_graph()
    else:
        from jobpilot_agent.evaluation.runners.baseline_runner import get_baseline_graph
        graph = get_baseline_graph()

    print(f"[3/3] 开始评估（并发={args.concurrency}）...")
    runner = ScenarioARunner(graph=graph, label=args.mode)
    records = await runner.run_all(
        dataset,
        concurrency=args.concurrency,
        output_path=output_path,
        checkpoint_every=args.checkpoint_every,
    )

    success = sum(1 for r in records if r.success)
    print(f"\n[完成] 共 {len(records)} 条，成功 {success}，失败 {len(records) - success}")
    print(f"       结果已写入：{output_path}")
    print(f"\n下一步：运行报告生成")
    print(f"  uv run python scripts/render_scenario_a_report.py \\")
    print(f"    --main <main_jsonl> --baseline <baseline_jsonl>")


if __name__ == "__main__":
    asyncio.run(main())
