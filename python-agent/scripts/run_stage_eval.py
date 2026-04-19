#!/usr/bin/env python
"""阶段推进准确率评估 CLI。

子命令：
  run            对结构化面经运行阶段预测，输出结果 JSONL
  render         从结果 JSONL 生成 Markdown 报告 + 混淆矩阵 PNG
  run-and-render 一步完成评估 + 报告生成

用法示例：
  # 快速冒烟（30 条面经）
  uv run python scripts/run_stage_eval.py run \\
    --max-interviews 30 --samples-per-interview 3 \\
    --output evaluation/stage/results_smoke.jsonl

  # 全量 300 条
  uv run python scripts/run_stage_eval.py run \\
    --max-interviews 300 --samples-per-interview 3 \\
    --output evaluation/stage/results_v1.jsonl

  # 生成报告
  uv run python scripts/run_stage_eval.py render \\
    --results evaluation/stage/results_v1.jsonl \\
    --output evaluation/reports/stage_prediction_v1.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_src = Path(__file__).resolve().parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


# ── run ────────────────────────────────────────────────────────────────────


def cmd_run(args: argparse.Namespace) -> None:
    from jobpilot_agent.evaluation.replay.loader import load_replay_dataset
    from jobpilot_agent.evaluation.stage.runner import StageEvaluator, StagePredictor
    from jobpilot_agent.graphs.interview.interviewer_core import get_interviewer_core

    interviews = load_replay_dataset(args.input or None)
    if args.max_interviews:
        interviews = interviews[: args.max_interviews]
    print(f"Loaded {len(interviews)} interviews")

    core = get_interviewer_core()
    predictor = StagePredictor(core=core)
    evaluator = StageEvaluator(
        predictor=predictor,
        concurrency=args.concurrency,
        seed=42,
    )

    result = asyncio.run(
        evaluator.evaluate(
            interviews,
            samples_per_interview=args.samples_per_interview,
        )
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result.model_dump_json(), encoding="utf-8")

    print(f"\nDone: {result.total_samples} samples")
    print(f"  Accuracy : {result.accuracy:.4f} ({'✅' if result.accuracy >= 0.85 else '❌'} target 0.85)")
    for lbl in result.labels_order:
        f1 = result.per_stage_f1.get(lbl, 0)
        print(f"  {lbl:22s} F1={f1:.4f}")
    print(f"Results written to {out}")


# ── render ─────────────────────────────────────────────────────────────────


def cmd_render(args: argparse.Namespace) -> None:
    from jobpilot_agent.evaluation.stage.metrics import StageEvalResult
    from jobpilot_agent.evaluation.stage.renderer import (
        generate_confusion_matrix_plot,
        generate_report,
    )

    results_path = Path(args.results)
    if not results_path.exists():
        print(f"Error: results file not found: {results_path}", file=sys.stderr)
        sys.exit(1)

    result = StageEvalResult.model_validate_json(results_path.read_text(encoding="utf-8"))
    print(f"Loaded result: {result.total_samples} samples, accuracy={result.accuracy:.4f}")

    out_path = Path(args.output)
    figures_dir = out_path.parent / "figures"

    figures: dict[str, Path] = {}
    png = generate_confusion_matrix_plot(result, figures_dir)
    if png:
        figures["confusion_matrix"] = png
        print(f"Confusion matrix saved to {png}")

    generate_report(result, out_path, figures=figures)
    print(f"Report written to {out_path}")
    print(f"\n  Accuracy : {result.accuracy:.4f}")
    for lbl in result.labels_order:
        f1 = result.per_stage_f1.get(lbl, 0)
        print(f"  {lbl:22s} F1={f1:.4f}")


# ── run-and-render ──────────────────────────────────────────────────────────


def cmd_run_and_render(args: argparse.Namespace) -> None:
    cmd_run(args)
    # reuse --output as --results for render
    render_args = argparse.Namespace(
        results=args.output,
        output=args.report_output or str(
            Path(args.output).parent.parent / "reports" / "stage_prediction_v1.md"
        ),
    )
    cmd_render(render_args)


# ── CLI entry ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="阶段推进准确率评估",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # run
    p_run = sub.add_parser("run", help="运行阶段预测评估")
    p_run.add_argument("--input", type=str, default=None, help="面经 JSONL 路径（默认内置）")
    p_run.add_argument("--output", type=str, default="evaluation/stage/results_v1.jsonl")
    p_run.add_argument("--max-interviews", type=int, default=None, help="最多使用几条面经")
    p_run.add_argument("--samples-per-interview", type=int, default=3)
    p_run.add_argument("--concurrency", type=int, default=5)

    # render
    p_render = sub.add_parser("render", help="生成报告")
    p_render.add_argument("--results", type=str, required=True)
    p_render.add_argument("--output", type=str, default="evaluation/reports/stage_prediction_v1.md")

    # run-and-render
    p_all = sub.add_parser("run-and-render", help="一步评估 + 生成报告")
    p_all.add_argument("--input", type=str, default=None)
    p_all.add_argument("--output", type=str, default="evaluation/stage/results_v1.jsonl")
    p_all.add_argument("--report-output", type=str, default=None)
    p_all.add_argument("--max-interviews", type=int, default=None)
    p_all.add_argument("--samples-per-interview", type=int, default=3)
    p_all.add_argument("--concurrency", type=int, default=5)

    args = parser.parse_args()
    if args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "render":
        cmd_render(args)
    elif args.cmd == "run-and-render":
        cmd_run_and_render(args)


if __name__ == "__main__":
    main()
