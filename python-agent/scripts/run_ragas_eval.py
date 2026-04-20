"""RAGAS 评估四件套 CLI。

子命令：
  build    — 构造 100 条评估集（分层抽样 + LLM 辅助 ground_truth）
  collect  — 跑 JD 路由图收集 contexts + answers
  evaluate — 跑 RAGAS 四件套计算指标
  render   — 生成 Markdown 报告 + 两张 PNG

用法示例：
  # 1. 构建评估集
  uv run python scripts/run_ragas_eval.py build \\
    --input ../knowledge-base/data/labeled/jd_labeled.jsonl \\
    --output evaluation/ragas/examples_v1.jsonl \\
    --size 100 --human-sampled 30

  # 2. 收集 contexts（先 --limit 10 验证）
  uv run python scripts/run_ragas_eval.py collect \\
    --input evaluation/ragas/examples_v1.jsonl \\
    --output evaluation/ragas/examples_with_context_v1.jsonl \\
    --concurrency 3

  # 3. 小样本验证（10 条）
  uv run python scripts/run_ragas_eval.py evaluate \\
    --input evaluation/ragas/examples_with_context_v1.jsonl \\
    --output evaluation/ragas/results_smoke.jsonl --limit 10

  # 4. 全量评估
  uv run python scripts/run_ragas_eval.py evaluate \\
    --input evaluation/ragas/examples_with_context_v1.jsonl \\
    --output evaluation/ragas/results_v1.jsonl

  # 5. 生成报告
  uv run python scripts/run_ragas_eval.py render \\
    --examples evaluation/ragas/examples_with_context_v1.jsonl \\
    --results evaluation/ragas/results_v1.jsonl \\
    --output evaluation/reports/ragas_v1.md
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


# ── 子命令实现 ─────────────────────────────────────────────────────────────────


async def cmd_build(args: argparse.Namespace) -> None:
    from jobpilot_agent.evaluation.ragas.dataset_builder import RagasDatasetBuilder

    builder = RagasDatasetBuilder(
        jd_labeled_path=args.input,
        output_path=args.output,
        size=args.size,
        human_sampled=args.human_sampled,
        seed=args.seed,
    )
    examples = await builder.build()
    print(f"✅ 评估集构造完成：{len(examples)} 条 → {args.output}")
    human = sum(1 for e in examples if e.ground_truth_source == "human")
    llm = sum(1 for e in examples if e.ground_truth_source == "llm_assisted")
    print(f"   人工标注：{human} 条（ground_truth 为空，待手动填写）")
    print(f"   LLM 辅助：{llm} 条")
    if human > 0:
        print(f"\n⚠️  请打开 {args.output}，为前 {human} 条补全 ground_truth 字段后再运行 collect。")


async def cmd_collect(args: argparse.Namespace) -> None:
    from jobpilot_agent.evaluation.ragas.dataset_builder import load_examples, save_examples
    from jobpilot_agent.evaluation.ragas.ragas_runner import RagasCollector
    from jobpilot_agent.graphs.jd_routing_graph import get_jd_routing_graph
    from jobpilot_agent.skills.registry import register_all_skills

    register_all_skills()
    examples = load_examples(args.input)
    print(f"[collect] 加载 {len(examples)} 条样本")

    if args.limit:
        examples = examples[: args.limit]
        print(f"[collect] 限制前 {args.limit} 条")

    graph = get_jd_routing_graph()
    collector = RagasCollector(graph)
    enriched = await collector.collect(
        examples,
        concurrency=args.concurrency,
        output_path=args.output,
        checkpoint_every=args.checkpoint_every,
    )

    ctx_filled = sum(1 for e in enriched if e.contexts)
    print(f"✅ collect 完成：{ctx_filled}/{len(enriched)} 条有 contexts → {args.output}")


async def cmd_evaluate(args: argparse.Namespace) -> None:
    from jobpilot_agent.evaluation.ragas.dataset_builder import load_examples
    from jobpilot_agent.evaluation.ragas.ragas_runner import RagasEvaluator, save_results

    examples = load_examples(args.input)
    print(f"[evaluate] 加载 {len(examples)} 条样本")

    evaluator = RagasEvaluator()
    results = await evaluator.evaluate(examples, limit=args.limit)
    save_results(results, args.output)

    successful = [r for r in results if r.error is None]
    if successful:
        cr = sum(r.context_relevancy for r in successful) / len(successful)
        cre = sum(r.context_recall for r in successful) / len(successful)
        fai = sum(r.faithfulness for r in successful) / len(successful)
        ar = sum(r.answer_relevancy for r in successful) / len(successful)
        print(f"✅ evaluate 完成：{len(successful)}/{len(results)} 条成功")
        print(f"   Context Relevance  = {cr:.3f} (target > 0.75)")
        print(f"   Context Recall     = {cre:.3f} (target > 0.80)")
        print(f"   Faithfulness       = {fai:.3f} (target > 0.85)")
        print(f"   Answer Relevancy   = {ar:.3f} (target > 0.80)")
    print(f"   结果写入 → {args.output}")


def cmd_render(args: argparse.Namespace) -> None:
    from jobpilot_agent.evaluation.ragas.dataset_builder import load_examples
    from jobpilot_agent.evaluation.ragas.ragas_runner import load_results
    from jobpilot_agent.evaluation.ragas.renderer import render

    examples = load_examples(args.examples)
    results = load_results(args.results)
    print(f"[render] {len(examples)} 样本 × {len(results)} 结果")

    agg = render(examples, results, args.output)
    print(f"✅ 报告生成完成 → {args.output}")
    print(f"   图表目录 → {Path(args.output).parent / 'figures'}/")
    print(f"   CR={agg.mean_context_relevancy:.3f}  CRE={agg.mean_context_recall:.3f}  "
          f"FAI={agg.mean_faithfulness:.3f}  AR={agg.mean_answer_relevancy:.3f}")


# ── CLI 入口 ───────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_ragas_eval",
        description="RAGAS 检索评估四件套 CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # build
    p_build = sub.add_parser("build", help="构造评估集（分层抽样 + LLM ground_truth）")
    p_build.add_argument("--input", required=True, help="jd_labeled.jsonl 路径")
    p_build.add_argument("--output", required=True, help="输出 JSONL 路径")
    p_build.add_argument("--size", type=int, default=100, help="样本总数（默认 100）")
    p_build.add_argument("--human-sampled", type=int, default=30, help="前 N 条待人工标注（默认 30）")
    p_build.add_argument("--seed", type=int, default=42, help="随机种子（默认 42）")

    # collect
    p_collect = sub.add_parser("collect", help="跑 JD 路由图收集 contexts + answers")
    p_collect.add_argument("--input", required=True, help="examples JSONL 路径")
    p_collect.add_argument("--output", required=True, help="输出带 contexts 的 JSONL 路径")
    p_collect.add_argument("--concurrency", type=int, default=3, help="并发数（默认 3）")
    p_collect.add_argument("--checkpoint-every", type=int, default=10, help="每 N 条写盘（默认 10）")
    p_collect.add_argument("--limit", type=int, default=None, help="限制处理前 N 条（smoke test 用）")

    # evaluate
    p_eval = sub.add_parser("evaluate", help="跑 RAGAS 四件套")
    p_eval.add_argument("--input", required=True, help="带 contexts 的 JSONL 路径")
    p_eval.add_argument("--output", required=True, help="结果 JSONL 路径")
    p_eval.add_argument("--limit", type=int, default=None, help="限制前 N 条（smoke test 用）")

    # render
    p_render = sub.add_parser("render", help="生成 Markdown 报告 + PNG 图")
    p_render.add_argument("--examples", required=True, help="带 contexts 的 JSONL 路径")
    p_render.add_argument("--results", required=True, help="results JSONL 路径")
    p_render.add_argument("--output", required=True, help="输出 Markdown 报告路径")

    return parser


def main() -> None:
    # 把 python-agent/src 加入 sys.path（在 uv run 环境下通常已安装，此处兜底）
    src_path = str(Path(__file__).parent.parent / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == "build":
        asyncio.run(cmd_build(args))
    elif args.cmd == "collect":
        asyncio.run(cmd_collect(args))
    elif args.cmd == "evaluate":
        asyncio.run(cmd_evaluate(args))
    elif args.cmd == "render":
        cmd_render(args)


if __name__ == "__main__":
    main()
