#!/usr/bin/env python
"""性能 Baseline 画像脚本（P6.1 步骤 1）。

对 N 条 JD 跑主图 jd_routing_graph，按 node/skill 维度聚合延迟与 token，
产出结构化 JSONL + 可读的 Markdown 报告。

设计原则：
- 不依赖 cProfile/snakeviz（跨进程聚合麻烦）；直接利用节点已写入的
  `state["metadata"][<node>]["latency_ms"]` 和 `skill_outputs[i]["latency_ms"]`
- 支持 --label 为不同优化轮次打标（baseline / after_cache / after_prompt_trim），
  多次跑后可横向对比
- 失败样本不计入 latency 统计，但保留在 JSONL 中供排错

用法：
    # 先跑 10 条烟雾测试
    uv run python scripts/profile_baseline.py --n 10 --label smoke

    # 跑完整 baseline（100 条）
    uv run python scripts/profile_baseline.py --n 100 --label baseline_v1

    # 某个优化完成后跑对比
    uv run python scripts/profile_baseline.py --n 100 --label after_cache

    # 跑完后生成对比报告
    uv run python scripts/profile_baseline.py --compare baseline_v1 after_cache
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

_src = Path(__file__).resolve().parents[1] / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

_PROFILE_DIR = Path(__file__).resolve().parents[1] / "docs" / "performance" / "runs"


def _pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * q
    f = int(k)
    c = min(f + 1, len(sorted_v) - 1)
    if f == c:
        return sorted_v[f]
    return sorted_v[f] + (sorted_v[c] - sorted_v[f]) * (k - f)


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0}
    return {
        "count": len(values),
        "mean_ms": round(statistics.fmean(values), 1),
        "p50_ms": round(_pct(values, 0.50), 1),
        "p95_ms": round(_pct(values, 0.95), 1),
        "p99_ms": round(_pct(values, 0.99), 1),
        "max_ms": round(max(values), 1),
    }


async def _run_one(graph: Any, sample: dict[str, Any]) -> dict[str, Any]:
    """对单条 JD 调 graph.ainvoke 并抽取 metadata。"""
    start = time.monotonic()
    initial_state: dict[str, Any] = {
        "jd_id": sample.get("jd_id"),
        "jd_text": sample["jd_text"],
        "user_context": {"preferred_lang": "zh"},
    }
    try:
        final_state = await graph.ainvoke(initial_state)
        success = True
        error = None
    except Exception as exc:  # noqa: BLE001
        final_state = {}
        success = False
        error = str(exc)

    total_ms = (time.monotonic() - start) * 1000
    metadata = (final_state or {}).get("metadata") or {}
    skill_outputs = (final_state or {}).get("skill_outputs") or []

    node_latency = {
        node: (info or {}).get("latency_ms", 0)
        for node, info in metadata.items()
        if isinstance(info, dict)
    }
    node_tokens = {
        node: (info or {}).get("tokens", 0)
        for node, info in metadata.items()
        if isinstance(info, dict) and (info or {}).get("tokens")
    }
    skill_latency = {
        so.get("skill_name"): so.get("latency_ms", 0)
        for so in skill_outputs
        if so.get("skill_name")
    }

    return {
        "jd_id": sample.get("jd_id"),
        "total_latency_ms": round(total_ms, 1),
        "success": success,
        "error": error,
        "node_latency_ms": node_latency,
        "skill_latency_ms": skill_latency,
        "node_tokens": node_tokens,
        "total_tokens": sum(node_tokens.values()),
        "invoked_skills": (final_state or {}).get("invoked_skills") or [],
    }


def _aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in records if r["success"]]
    total_lat = [r["total_latency_ms"] for r in ok]
    total_tok = [r["total_tokens"] for r in ok]

    per_node: dict[str, list[float]] = defaultdict(list)
    for r in ok:
        for node, ms in r["node_latency_ms"].items():
            per_node[node].append(ms)

    per_skill: dict[str, list[float]] = defaultdict(list)
    per_skill_count: dict[str, int] = defaultdict(int)
    for r in ok:
        for skill, ms in r["skill_latency_ms"].items():
            per_skill[skill].append(ms)
            per_skill_count[skill] += 1

    return {
        "total_samples": len(records),
        "success": len(ok),
        "failed": len(records) - len(ok),
        "end_to_end": _summary(total_lat),
        "token_stats": {
            "total_tokens": sum(total_tok),
            "mean_per_jd": round(statistics.fmean(total_tok), 1) if total_tok else 0.0,
        },
        "per_node": {node: _summary(lats) for node, lats in per_node.items()},
        "per_skill": {
            skill: {
                **_summary(per_skill[skill]),
                "invocation_rate": round(per_skill_count[skill] / len(ok), 3),
            }
            for skill in per_skill
        },
    }


def _render_markdown(label: str, agg: dict[str, Any], n: int) -> str:
    lines = [
        f"# 性能画像报告 — `{label}`",
        "",
        f"- 运行时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 样本数: {n}（成功 {agg['success']} / 失败 {agg['failed']}）",
        "",
        "## 端到端延迟",
        "",
        f"P50 = {agg['end_to_end']['p50_ms']} ms · P95 = {agg['end_to_end']['p95_ms']} ms · "
        f"P99 = {agg['end_to_end']['p99_ms']} ms · mean = {agg['end_to_end']['mean_ms']} ms",
        "",
        "## Token 成本",
        "",
        f"总 token = {agg['token_stats']['total_tokens']} · 平均每 JD = {agg['token_stats']['mean_per_jd']}",
        "",
        "## Node 级耗时",
        "",
        "| Node | count | mean | P50 | P95 | P99 | max |",
        "|---|---|---|---|---|---|---|",
    ]
    for node, st in sorted(agg["per_node"].items(), key=lambda x: -x[1]["mean_ms"]):
        lines.append(
            f"| {node} | {st['count']} | {st['mean_ms']} | {st['p50_ms']} | "
            f"{st['p95_ms']} | {st['p99_ms']} | {st['max_ms']} |"
        )

    lines += [
        "",
        "## Skill 级耗时",
        "",
        "| Skill | invocation_rate | count | mean | P50 | P95 | P99 |",
        "|---|---|---|---|---|---|---|",
    ]
    for skill, st in sorted(agg["per_skill"].items(), key=lambda x: -x[1]["mean_ms"]):
        lines.append(
            f"| {skill} | {st['invocation_rate']:.1%} | {st['count']} | "
            f"{st['mean_ms']} | {st['p50_ms']} | {st['p95_ms']} | {st['p99_ms']} |"
        )

    lines.append("")
    return "\n".join(lines)


def _compare(label_a: str, label_b: str) -> str:
    """生成两个 run 的对比报告。"""
    def _load(label: str) -> dict[str, Any]:
        p = _PROFILE_DIR / f"{label}.agg.json"
        if not p.exists():
            raise FileNotFoundError(f"找不到 {p}；先用 --label {label} 跑一次")
        return json.loads(p.read_text())

    a = _load(label_a)
    b = _load(label_b)

    def _delta_pct(old: float, new: float) -> str:
        if old == 0:
            return "-"
        pct = (new - old) / old * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"

    lines = [
        f"# 性能对比 — `{label_a}` → `{label_b}`",
        "",
        "## 端到端",
        "",
        "| 指标 | A | B | Δ |",
        "|---|---|---|---|",
    ]
    for metric in ("p50_ms", "p95_ms", "p99_ms", "mean_ms"):
        va = a["end_to_end"][metric]
        vb = b["end_to_end"][metric]
        lines.append(f"| {metric} | {va} | {vb} | {_delta_pct(va, vb)} |")

    lines += [
        "",
        f"**Token**: {a['token_stats']['total_tokens']} → {b['token_stats']['total_tokens']} "
        f"({_delta_pct(a['token_stats']['total_tokens'], b['token_stats']['total_tokens'])})",
        "",
        "## Node 级（按 A 的 P95 排序）",
        "",
        "| Node | A.P95 | B.P95 | Δ |",
        "|---|---|---|---|",
    ]
    nodes = sorted(
        set(a["per_node"]) | set(b["per_node"]),
        key=lambda n: -a["per_node"].get(n, {"p95_ms": 0})["p95_ms"],
    )
    for node in nodes:
        va = a["per_node"].get(node, {"p95_ms": 0})["p95_ms"]
        vb = b["per_node"].get(node, {"p95_ms": 0})["p95_ms"]
        lines.append(f"| {node} | {va} | {vb} | {_delta_pct(va, vb)} |")

    lines += [
        "",
        "## Skill 级（按 A 的 P95 排序）",
        "",
        "| Skill | A.P95 | B.P95 | Δ |",
        "|---|---|---|---|",
    ]
    skills = sorted(
        set(a["per_skill"]) | set(b["per_skill"]),
        key=lambda s: -a["per_skill"].get(s, {"p95_ms": 0})["p95_ms"],
    )
    for skill in skills:
        va = a["per_skill"].get(skill, {"p95_ms": 0})["p95_ms"]
        vb = b["per_skill"].get(skill, {"p95_ms": 0})["p95_ms"]
        lines.append(f"| {skill} | {va} | {vb} | {_delta_pct(va, vb)} |")

    lines.append("")
    return "\n".join(lines)


async def _run_profile(label: str, n: int, concurrency: int, dataset: str) -> None:
    from jobpilot_agent.evaluation.datasets.loader import load_jd_eval_dataset
    from jobpilot_agent.graphs.jd_routing_graph import get_jd_routing_graph

    print(f"[profile] label={label}, n={n}, concurrency={concurrency}")

    samples = load_jd_eval_dataset(path=dataset, sample_size=n)
    graph = get_jd_routing_graph()

    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []

    sem = asyncio.Semaphore(concurrency)

    async def _bounded(sample: dict[str, Any]) -> dict[str, Any]:
        async with sem:
            out = await _run_one(graph, sample)
            print(f"  [{out['jd_id']}] total={out['total_latency_ms']:.0f}ms success={out['success']}")
            return out

    # 解构 samples：兼容 list[dict] 和 pydantic 模型
    normalized = []
    for s in samples:
        if hasattr(s, "model_dump"):
            normalized.append(s.model_dump())
        elif isinstance(s, dict):
            normalized.append(s)
        else:
            normalized.append({"jd_id": getattr(s, "jd_id", None), "jd_text": getattr(s, "jd_text", "")})

    records = await asyncio.gather(*[_bounded(s) for s in normalized])

    # 落盘
    raw_path = _PROFILE_DIR / f"{label}.raw.jsonl"
    with raw_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    agg = _aggregate(records)
    agg_path = _PROFILE_DIR / f"{label}.agg.json"
    agg_path.write_text(json.dumps(agg, ensure_ascii=False, indent=2))

    md_path = _PROFILE_DIR / f"{label}.md"
    md_path.write_text(_render_markdown(label, agg, len(records)))

    print(f"\n[完成] raw -> {raw_path}")
    print(f"       agg -> {agg_path}")
    print(f"       md  -> {md_path}")
    print(f"\n端到端 P95 = {agg['end_to_end']['p95_ms']} ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="JobPilot 主图性能画像")
    parser.add_argument("--label", help="本轮打标（如 baseline_v1、after_cache）")
    parser.add_argument("--n", type=int, default=10, help="样本数（默认 10）")
    parser.add_argument("--concurrency", type=int, default=5, help="并发度（默认 5）")
    parser.add_argument(
        "--dataset",
        default="knowledge-base/data/labeled/jd_labeled.jsonl",
        help="JD 数据集路径",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("LABEL_A", "LABEL_B"),
        help="生成两轮对比 Markdown",
    )
    args = parser.parse_args()

    if args.compare:
        md = _compare(args.compare[0], args.compare[1])
        out = _PROFILE_DIR / f"compare_{args.compare[0]}_vs_{args.compare[1]}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(md)
        print(f"[compare] -> {out}")
        print(md)
        return

    if not args.label:
        parser.error("需要 --label 或 --compare")

    asyncio.run(
        _run_profile(
            label=args.label,
            n=args.n,
            concurrency=args.concurrency,
            dataset=args.dataset,
        )
    )


if __name__ == "__main__":
    main()
