#!/usr/bin/env python
"""生成场景 A 对比报告（指标计算 + 图表 + Markdown）。

用法：
    uv run python scripts/render_scenario_a_report.py \\
        --main evaluation/runs/main_20260501.jsonl \\
        --baseline evaluation/runs/baseline_20260501.jsonl \\
        --output evaluation/reports/scenario_a_v1.md

    # 仅主图（无 baseline 延迟/成本对比）
    uv run python scripts/render_scenario_a_report.py \\
        --main evaluation/runs/main_20260501.jsonl \\
        --output evaluation/reports/scenario_a_main_only.md

前置条件：
    已安装 eval 依赖：uv sync --extra eval
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_src = Path(__file__).resolve().parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


def main() -> None:
    parser = argparse.ArgumentParser(description="场景 A 报告生成器")
    parser.add_argument("--main", required=True, help="主图运行结果 JSONL 路径")
    parser.add_argument("--baseline", default=None, help="Baseline 运行结果 JSONL 路径")
    parser.add_argument(
        "--output",
        default="evaluation/reports/scenario_a_v1.md",
        help="报告输出路径（默认 evaluation/reports/scenario_a_v1.md）",
    )
    parser.add_argument(
        "--model",
        default="doubao-pro-4k",
        help="LLM 模型名称（写入报告头部）",
    )
    parser.add_argument(
        "--token-price",
        type=float,
        default=0.001,
        help="每千 token 费用（CNY，默认 0.001）",
    )
    args = parser.parse_args()

    from jobpilot_agent.evaluation.runners.scenario_a_runner import load_run_records

    print(f"[render] 加载主图记录：{args.main}")
    main_records = load_run_records(args.main)
    print(f"         共 {len(main_records)} 条（成功 {sum(1 for r in main_records if r.success)}）")

    if args.baseline:
        print(f"[render] 加载 Baseline 记录：{args.baseline}")
        baseline_records = load_run_records(args.baseline)
        print(f"         共 {len(baseline_records)} 条（成功 {sum(1 for r in baseline_records if r.success)}）")
    else:
        print("[render] 未提供 baseline，成本对比将使用估算值")
        baseline_records = []

    print("[render] 计算指标...")
    from jobpilot_agent.evaluation.metrics.classification import compute_classification_metrics
    from jobpilot_agent.evaluation.metrics.cost import compute_cost_comparison
    from jobpilot_agent.evaluation.metrics.latency import compute_latency_metrics
    from jobpilot_agent.evaluation.metrics.routing import compute_routing_metrics
    from jobpilot_agent.evaluation.datasets.loader import get_all_skill_names, load_jd_eval_dataset

    clf_metrics = compute_classification_metrics(main_records)
    print(f"         分类 joint_accuracy={clf_metrics.joint_accuracy:.3f}")

    all_skills = list({s for r in main_records for s in r.ground_truth_expected_skills + r.ground_truth_forbidden_skills})
    routing_metrics = compute_routing_metrics(main_records, all_skill_names=all_skills)
    print(f"         路由 macro_f1={routing_metrics.macro_f1:.3f}, over_inv={routing_metrics.over_invocation_rate:.3f}")

    main_latency = compute_latency_metrics(main_records)
    print(f"         延迟 P95={main_latency.p95_ms:.0f}ms")

    if baseline_records:
        baseline_latency = compute_latency_metrics(baseline_records)
    else:
        # 无 baseline 时构建占位延迟指标
        from jobpilot_agent.evaluation.metrics.latency import LatencyMetrics
        baseline_latency = LatencyMetrics(
            p50_ms=0, p90_ms=0, p95_ms=0, p99_ms=0,
            mean_ms=0, max_ms=0, min_ms=0,
            evaluated_count=0, per_node={},
        )

    cost = compute_cost_comparison(main_records, baseline_records, token_price_per_1k_cny=args.token_price)
    print(f"         Token 降幅={cost.token_reduction_pct * 100:.1f}%")

    output_path = Path(args.output)
    figures_dir = output_path.parent

    print("[render] 生成图表...")
    from jobpilot_agent.evaluation.reports.plots import generate_all_plots
    plot_paths = generate_all_plots(
        clf_metrics=clf_metrics,
        routing_metrics=routing_metrics,
        main_latency=main_latency,
        baseline_latency=baseline_latency,
        cost=cost,
        main_records=main_records,
        baseline_records=baseline_records,
        output_dir=figures_dir,
    )
    for k, v in plot_paths.items():
        if isinstance(v, list):
            print(f"         {k}: {len(v)} 张图")
        else:
            print(f"         {k}: {v}")

    print(f"[render] 生成报告：{args.output}")
    from jobpilot_agent.evaluation.reports.renderer import generate_report
    generate_report(
        clf_metrics=clf_metrics,
        routing_metrics=routing_metrics,
        main_latency=main_latency,
        baseline_latency=baseline_latency,
        cost=cost,
        main_records=main_records,
        baseline_records=baseline_records,
        output_path=args.output,
        model_name=args.model,
    )

    print(f"\n[完成] 报告已生成：{args.output}")
    print("       包含以下章节：摘要 | 分类 | 路由 | 延迟 | 成本 | 错误分析")


if __name__ == "__main__":
    main()
