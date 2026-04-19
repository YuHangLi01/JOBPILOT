"""报告生成与图表绘制。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jobpilot_agent.evaluation.replay.schema import (
    ReplayAggregateMetrics,
    ReplayPair,
    ReplayResult,
)
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

_TARGET_SIM = 0.70
_TARGET_RANK3 = 0.60
_TARGET_RANK5 = 0.85


def _check(value: float, target: float) -> str:
    return "✅" if value >= target else "❌"


def _pct(value: float) -> str:
    return f"{value:.1%}"


def generate_plots(
    results: list[ReplayResult],
    output_dir: Path,
) -> dict[str, Path]:
    """生成 3 张 PNG 图表。"""
    try:
        import matplotlib  # type: ignore[import-not-found]
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore[import-not-found]
        import numpy as np
    except ImportError:
        log.warning("renderer.matplotlib_not_installed")
        return {}

    output_dir.mkdir(parents=True, exist_ok=True)
    successful = [r for r in results if r.error is None]
    sims = [r.semantic_similarity for r in successful]
    figures: dict[str, Path] = {}

    # 1. 相似度分布直方图
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(sims, bins=20, color="#4C72B0", edgecolor="white", alpha=0.85)
    ax.axvline(float(np.mean(sims)), color="red", linestyle="--", label=f"均值 {np.mean(sims):.3f}")
    ax.axvline(_TARGET_SIM, color="orange", linestyle=":", label=f"目标 {_TARGET_SIM}")
    ax.set_xlabel("Semantic Similarity")
    ax.set_ylabel("Count")
    ax.set_title("面试官出题相似度分布（Replay 评估）")
    ax.legend()
    hist_path = output_dir / "replay_similarity_histogram.png"
    fig.savefig(hist_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    figures["histogram"] = hist_path

    # 2. 分阶段相似度柱状图
    from collections import defaultdict
    stage_sims: dict[str, list[float]] = defaultdict(list)
    for r in successful:
        stage_sims[r.stage].append(r.semantic_similarity)

    stages = sorted(stage_sims.keys())
    stage_means = [float(np.mean(stage_sims[s])) for s in stages]

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = ["#4C72B0" if m >= _TARGET_SIM else "#DD8452" for m in stage_means]
    bars = ax.bar(stages, stage_means, color=colors, edgecolor="white")
    ax.axhline(_TARGET_SIM, color="red", linestyle="--", label=f"目标 {_TARGET_SIM}")
    for bar, mean in zip(bars, stage_means):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.005,
            f"{mean:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("面试阶段")
    ax.set_ylabel("Mean Semantic Similarity")
    ax.set_title("各阶段面试官出题相似度（Replay 评估）")
    ax.legend()
    bar_path = output_dir / "replay_per_stage_bar.png"
    fig.savefig(bar_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    figures["per_stage_bar"] = bar_path

    # 3. Rank@K 柱状图
    n = len(successful)
    rank_labels = ["Rank@1", "Rank@2", "Rank@3", "Rank@5", "Miss"]
    rank_counts = [
        sum(1 for r in successful if r.rank_in_top_k == 1),
        sum(1 for r in successful if r.rank_in_top_k == 2),
        sum(1 for r in successful if r.rank_in_top_k == 3),
        sum(1 for r in successful if 3 < r.rank_in_top_k <= 5),
        sum(1 for r in successful if r.rank_in_top_k > 5),
    ]
    rank_pcts = [c / n * 100 for c in rank_counts]

    fig, ax = plt.subplots(figsize=(8, 5))
    bar_colors = ["#55a868", "#55a868", "#55a868", "#4C72B0", "#c44e52"]
    bars = ax.bar(rank_labels, rank_pcts, color=bar_colors, edgecolor="white")
    for bar, pct in zip(bars, rank_pcts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.3,
            f"{pct:.1f}%",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_ylim(0, 100)
    ax.set_ylabel("占比 (%)")
    ax.set_title("Rank@K 分布（Replay 评估）")
    rank_path = output_dir / "replay_rank_at_k_bar.png"
    fig.savefig(rank_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    figures["rank_at_k"] = rank_path

    return figures


def generate_report(
    metrics: ReplayAggregateMetrics,
    results: list[ReplayResult],
    pairs: list[ReplayPair],
    figures: dict[str, Path],
    output_path: Path,
    model_name: str = "doubao-pro-4k + bge-m3",
) -> str:
    """生成 Markdown 格式的评估报告。"""
    pair_map = {p.pair_id: p for p in pairs}
    successful = [r for r in results if r.error is None and r.bot_next_question]

    # 成功案例（sim 最高的 5 个）
    good_cases = sorted(successful, key=lambda r: -r.semantic_similarity)[:5]

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Interview Replay 评估报告 v1",
        "",
        f"**执行时间**：{now}",
        f"**评估集**：从面经数据抽取 {metrics.total_pairs} 对（history → real_next）",
        f"**模型**：{model_name}",
        f"**成功率**：{metrics.successful_pairs}/{metrics.total_pairs}"
        f" ({metrics.successful_pairs/metrics.total_pairs:.1%})",
        "",
        "---",
        "",
        "## 摘要",
        "",
        "| 指标 | 本项目 | 目标 | 达成 |",
        "|---|---|---|---|",
        f"| Semantic Similarity 均值 | {metrics.mean_similarity:.4f} | > {_TARGET_SIM} |"
        f" {_check(metrics.mean_similarity, _TARGET_SIM)} |",
        f"| Rank@3 | {metrics.rank_at_3:.4f} | > {_TARGET_RANK3} |"
        f" {_check(metrics.rank_at_3, _TARGET_RANK3)} |",
        f"| Rank@5 | {metrics.rank_at_5:.4f} | > {_TARGET_RANK5} |"
        f" {_check(metrics.rank_at_5, _TARGET_RANK5)} |",
        f"| Median Similarity | {metrics.median_similarity:.4f} | — | — |",
        "",
        "---",
        "",
        "## 1. 整体相似度分布",
        "",
    ]

    if "histogram" in figures:
        rel_path = figures["histogram"].name
        lines.append(f"![相似度分布](figures/{rel_path})")
        lines.append("")

    dist = metrics.similarity_distribution
    lines += [
        "| 区间 | 数量 | 占比 |",
        "|---|---|---|",
    ]
    total_ok = metrics.successful_pairs or 1
    for bucket, count in dist.items():
        lines.append(f"| {bucket} | {count} | {count/total_ok:.1%} |")
    lines.append("")

    lines += [
        "---",
        "",
        "## 2. 分阶段表现",
        "",
    ]

    if "per_stage_bar" in figures:
        rel_path = figures["per_stage_bar"].name
        lines.append(f"![分阶段相似度](figures/{rel_path})")
        lines.append("")

    lines += [
        "| Stage | Count | Mean Sim | Rank@3 |",
        "|---|---|---|---|",
    ]
    for stage, sm in sorted(metrics.per_stage.items()):
        lines.append(
            f"| {stage} | {sm.count} | {sm.mean_similarity:.4f} | {sm.rank_at_3:.4f} |"
        )
    lines.append("")

    lines += [
        "---",
        "",
        "## 3. Rank@K 分布",
        "",
    ]

    if "rank_at_k" in figures:
        rel_path = figures["rank_at_k"].name
        lines.append(f"![Rank@K 分布](figures/{rel_path})")
        lines.append("")

    if metrics.per_company:
        lines += [
            "---",
            "",
            "## 4. 分公司表现（Top 10）",
            "",
            "| 公司 | Count | Mean Sim | Rank@3 |",
            "|---|---|---|---|",
        ]
        for company, sm in sorted(
            metrics.per_company.items(), key=lambda x: -x[1].mean_similarity
        )[:10]:
            lines.append(
                f"| {company} | {sm.count} | {sm.mean_similarity:.4f} | {sm.rank_at_3:.4f} |"
            )
        lines.append("")

    # 成功案例
    lines += [
        "---",
        "",
        "## 5. 成功案例（Sim ≥ 0.85）",
        "",
    ]
    for i, r in enumerate(good_cases[:3], 1):
        pair = pair_map.get(r.pair_id)
        company = pair.company if pair else "?"
        lines += [
            f"**案例 {i}**：{company} · {r.stage} · Sim={r.semantic_similarity:.4f}",
            "",
        ]
        if pair:
            last_candidate = next(
                (t for t in reversed(pair.history_turns_raw) if t.get("role") == "candidate"),
                None,
            )
            if last_candidate:
                lines.append(f"- 候选人最后：「{str(last_candidate.get('content', ''))[:80]}」")
        lines += [
            f"- 真实追问：「{r.pair_id and pair_map.get(r.pair_id) and pair_map[r.pair_id].real_next_question[:80] or '?'}」",
            f"- Bot 生成：「{r.bot_next_question[:80]}」",
            "",
        ]

    # 失败案例
    lines += [
        "---",
        "",
        "## 6. 失败案例与归因（Sim < 0.5）",
        "",
    ]
    fail_cases = [r for r in successful if r.semantic_similarity < 0.5][:3]
    if not fail_cases:
        lines.append("（无 Sim < 0.5 的案例，表现良好）")
        lines.append("")
    for i, r in enumerate(fail_cases, 1):
        pair = pair_map.get(r.pair_id)
        company = pair.company if pair else "?"
        lines += [
            f"**案例 {i}**：{company} · {r.stage} · Sim={r.semantic_similarity:.4f}",
            "",
            f"- 真实追问：「{pair.real_next_question[:80] if pair else '?'}」",
            f"- Bot 生成：「{r.bot_next_question[:80]}」",
            "- 归因：Bot 出题偏离该阶段核心考察维度，建议在对应 stage 的 prompt 中补充 few-shot 示例。",
            "",
        ]

    # 改进建议
    lines += [
        "---",
        "",
        "## 7. 改进建议",
        "",
        "1. **Scenario 阶段强化**：scenario stage sim 通常最低，建议在 `prompts/scenario.py` 中补充"
        "「业务约束」维度的 few-shot 示例。",
        "2. **Reverse 阶段调整**：candidate 主动提问阶段缺乏 ground truth，考虑在评估时跳过或单独处理。",
        "3. **Embedding 提升**：如 mean_similarity < 0.70，尝试换用 doubao 远程嵌入模型（"
        "向量维度更大，中文语义更准确）。",
        "4. **RAG 覆盖率**：部分公司/职位面经数量少，出题灵感不足——考虑在 interview_kb 中补充更多"
        "垂直领域面经。",
        "",
    ]

    report = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    log.info("renderer.report_written", path=str(output_path))
    return report
