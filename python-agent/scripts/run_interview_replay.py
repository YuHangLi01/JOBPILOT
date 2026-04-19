#!/usr/bin/env python
"""Interview Replay 评估 CLI。

子命令：
  extract-pairs  从面经抽取评估对，落盘 JSONL
  run            并发执行 Replay，支持断点续跑
  render         从结果 JSONL 生成报告 + 图表

用法示例：
  # 小样本验证（推荐先跑 30 对）
  uv run python scripts/run_interview_replay.py extract-pairs --target-count 30 \\
    --output evaluation/replay/pairs_smoke.jsonl
  uv run python scripts/run_interview_replay.py run \\
    --pairs evaluation/replay/pairs_smoke.jsonl \\
    --output evaluation/replay/results_smoke.jsonl --concurrency 3

  # 全量 500 对
  uv run python scripts/run_interview_replay.py extract-pairs --target-count 500 \\
    --output evaluation/replay/pairs_v1.jsonl
  uv run python scripts/run_interview_replay.py run \\
    --pairs evaluation/replay/pairs_v1.jsonl \\
    --output evaluation/replay/results_v1.jsonl --concurrency 3
  uv run python scripts/run_interview_replay.py render \\
    --results evaluation/replay/results_v1.jsonl \\
    --pairs evaluation/replay/pairs_v1.jsonl \\
    --output evaluation/reports/interview_replay_v1.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_src = Path(__file__).resolve().parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))


# ── extract-pairs ──────────────────────────────────────────────────────────


def cmd_extract_pairs(args: argparse.Namespace) -> None:
    from jobpilot_agent.evaluation.replay.loader import load_replay_dataset
    from jobpilot_agent.evaluation.replay.sampling import extract_replay_pairs, stratified_sample

    print(f"Loading dataset from: {args.input or '(default)'}")
    interviews = load_replay_dataset(args.input or None)
    print(f"  → {len(interviews)} interviews loaded (quality_score >= 0.6)")

    all_pairs = extract_replay_pairs(
        interviews,
        min_history_turns=args.min_history,
        max_pairs_per_interview=args.max_per_interview,
    )
    print(f"  → {len(all_pairs)} raw pairs extracted")

    sampled = stratified_sample(all_pairs, target_count=args.target_count)
    print(f"  → {len(sampled)} pairs after stratified sampling (target={args.target_count})")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for pair in sampled:
            f.write(pair.model_dump_json() + "\n")
    print(f"  → Written to {out}")


# ── run ────────────────────────────────────────────────────────────────────


def cmd_run(args: argparse.Namespace) -> None:
    from jobpilot_agent.evaluation.replay.loader import load_replay_pairs_from_jsonl
    from jobpilot_agent.evaluation.replay.runner import ReplayRunner
    from jobpilot_agent.evaluation.replay.schema import ReplayPair
    from jobpilot_agent.graphs.interview.interviewer_core import get_interviewer_core
    from jobpilot_agent.retrieval.embedding import get_embedder

    pairs_path = Path(args.pairs)
    if not pairs_path.exists():
        print(f"Error: pairs file not found: {pairs_path}", file=sys.stderr)
        sys.exit(1)

    # 加载 pairs
    pairs: list[ReplayPair] = load_replay_pairs_from_jsonl(pairs_path)  # type: ignore[assignment]
    print(f"Loaded {len(pairs)} pairs from {pairs_path}")

    core = get_interviewer_core()
    embedder = get_embedder()
    runner = ReplayRunner(core=core, embedder=embedder, concurrency=args.concurrency)

    results = asyncio.run(runner.run_all(pairs, output_path=args.output))

    success = sum(1 for r in results if r.error is None)
    print(f"\nDone: {len(results)} pairs, {success} successful ({success/max(len(results),1):.1%})")

    # 快速指标预览
    from jobpilot_agent.evaluation.replay.metrics import aggregate_metrics

    if results:
        agg = aggregate_metrics(results)
        print(f"  Mean Similarity : {agg.mean_similarity:.4f}")
        print(f"  Rank@3          : {agg.rank_at_3:.4f}")
        print(f"  Rank@5          : {agg.rank_at_5:.4f}")


# ── render ─────────────────────────────────────────────────────────────────


def cmd_render(args: argparse.Namespace) -> None:
    from jobpilot_agent.evaluation.replay.loader import (
        load_replay_pairs_from_jsonl,
        load_replay_results_from_jsonl,
    )
    from jobpilot_agent.evaluation.replay.metrics import aggregate_metrics_with_pairs
    from jobpilot_agent.evaluation.replay.renderer import generate_plots, generate_report
    from jobpilot_agent.evaluation.replay.schema import ReplayPair, ReplayResult

    results: list[ReplayResult] = load_replay_results_from_jsonl(args.results)  # type: ignore[assignment]
    pairs: list[ReplayPair] = []
    if args.pairs and Path(args.pairs).exists():
        pairs = load_replay_pairs_from_jsonl(args.pairs)  # type: ignore[assignment]
    print(f"Loaded {len(results)} results, {len(pairs)} pairs")

    metrics = aggregate_metrics_with_pairs(results, pairs)

    out_path = Path(args.output)
    figures_dir = out_path.parent / "figures"
    figures = generate_plots(results, output_dir=figures_dir)
    print(f"Generated {len(figures)} figures in {figures_dir}")

    generate_report(
        metrics=metrics,
        results=results,
        pairs=pairs,
        figures=figures,
        output_path=out_path,
    )
    print(f"Report written to {out_path}")
    # 打印摘要
    print(f"\n  Mean Sim  : {metrics.mean_similarity:.4f}")
    print(f"  Median Sim: {metrics.median_similarity:.4f}")
    print(f"  Rank@3    : {metrics.rank_at_3:.4f}")
    print(f"  Rank@5    : {metrics.rank_at_5:.4f}")


# ── CLI entry ──────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interview Replay 评估",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # extract-pairs
    p_extract = sub.add_parser("extract-pairs", help="抽取评估对")
    p_extract.add_argument("--input", type=str, default=None, help="面经 JSONL 路径（默认内置）")
    p_extract.add_argument("--output", type=str, default="evaluation/replay/pairs_v1.jsonl")
    p_extract.add_argument("--target-count", type=int, default=500)
    p_extract.add_argument("--min-history", type=int, default=2)
    p_extract.add_argument("--max-per-interview", type=int, default=5)

    # run
    p_run = sub.add_parser("run", help="执行 Replay 评估")
    p_run.add_argument("--pairs", type=str, required=True, help="pairs JSONL 路径")
    p_run.add_argument("--output", type=str, default="evaluation/replay/results_v1.jsonl")
    p_run.add_argument("--concurrency", type=int, default=3)

    # render
    p_render = sub.add_parser("render", help="生成报告")
    p_render.add_argument("--results", type=str, required=True, help="results JSONL 路径")
    p_render.add_argument("--pairs", type=str, default=None, help="pairs JSONL 路径（用于公司维度）")
    p_render.add_argument("--output", type=str, default="evaluation/reports/interview_replay_v1.md")

    args = parser.parse_args()

    if args.cmd == "extract-pairs":
        cmd_extract_pairs(args)
    elif args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "render":
        cmd_render(args)


if __name__ == "__main__":
    main()
