"""评估报告图表生成。

产出 5 张 PNG（保存到 output_dir/figures/）：
1. classification_confusion_matrix_{field}.png  （5 个字段各一张）
2. routing_f1_per_skill_bar.png
3. latency_distribution_histogram.png  （主图 vs baseline）
4. cost_comparison_bar.png
5. five_dim_radar.png  ← 雷达图（答辩必用）

雷达图五维（均为「越大越好」）：
  - 分类准确率（joint_accuracy）
  - Skill 路由 F1（macro_f1）
  - 低 over-invocation（1 - over_invocation_rate）
  - 低延迟（1 - P95/ref_P95）
  - 低成本（1 - main_cost/baseline_cost）
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jobpilot_agent.evaluation.metrics.classification import ClassificationMetrics
    from jobpilot_agent.evaluation.metrics.cost import CostComparison
    from jobpilot_agent.evaluation.metrics.latency import LatencyMetrics
    from jobpilot_agent.evaluation.metrics.routing import RoutingMetrics
    from jobpilot_agent.evaluation.runners.scenario_a_runner import RunRecord


def _ensure_output_dir(output_dir: Path) -> Path:
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    return figures_dir


# ── 1. 混淆矩阵（5个字段） ─────────────────────────────────────────────────


def plot_confusion_matrices(
    clf_metrics: "ClassificationMetrics",
    output_dir: Path,
) -> list[Path]:
    """为每个分类字段绘制混淆矩阵热力图。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import seaborn as sns  # type: ignore[import]

    figures_dir = _ensure_output_dir(output_dir)
    paths: list[Path] = []

    for field, fm in clf_metrics.per_field.items():
        if not fm.confusion_matrix:
            continue
        cm = np.array(fm.confusion_matrix)
        labels = fm.labels_order

        fig, ax = plt.subplots(figsize=(max(5, len(labels)), max(4, len(labels) - 1)))
        sns.heatmap(
            cm,
            annot=True,
            fmt="d",
            cmap="Blues",
            xticklabels=labels,
            yticklabels=labels,
            ax=ax,
        )
        ax.set_xlabel("Predicted", fontsize=11)
        ax.set_ylabel("True", fontsize=11)
        ax.set_title(f"Confusion Matrix — {field}\n(Accuracy={fm.accuracy:.3f}, Macro F1={fm.macro_f1:.3f})", fontsize=12)
        plt.tight_layout()

        path = figures_dir / f"classification_confusion_matrix_{field}.png"
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        paths.append(path)

    return paths


# ── 2. Skill 路由 F1 柱状图 ─────────────────────────────────────────────────


def plot_routing_f1_bar(
    routing_metrics: "RoutingMetrics",
    output_dir: Path,
) -> Path:
    """绘制各 Skill F1 水平柱状图。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures_dir = _ensure_output_dir(output_dir)

    skills = sorted(routing_metrics.per_skill.keys())
    f1_scores = [routing_metrics.per_skill[s].f1 for s in skills]
    precisions = [routing_metrics.per_skill[s].precision for s in skills]
    recalls = [routing_metrics.per_skill[s].recall for s in skills]

    y = range(len(skills))
    fig, ax = plt.subplots(figsize=(9, max(4, len(skills) * 0.7)))

    bar_height = 0.25
    ax.barh([i + bar_height for i in y], precisions, bar_height, label="Precision", color="#4C72B0")
    ax.barh(y, recalls, bar_height, label="Recall", color="#DD8452")
    ax.barh([i - bar_height for i in y], f1_scores, bar_height, label="F1", color="#55A868")

    ax.set_yticks(list(y))
    ax.set_yticklabels(skills, fontsize=10)
    ax.set_xlim(0, 1.05)
    ax.set_xlabel("Score", fontsize=11)
    ax.set_title(
        f"Skill Routing Metrics per Skill\n"
        f"Macro F1={routing_metrics.macro_f1:.3f}  "
        f"Over-inv={routing_metrics.over_invocation_rate:.3f}  "
        f"Perfect={routing_metrics.perfect_match_rate:.3f}",
        fontsize=11,
    )
    ax.axvline(0.85, color="red", linestyle="--", linewidth=0.8, label="Target (0.85)")
    ax.legend(loc="lower right", fontsize=9)
    plt.tight_layout()

    path = figures_dir / "routing_f1_per_skill_bar.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


# ── 3. 延迟分布直方图（主图 vs Baseline） ─────────────────────────────────


def plot_latency_histogram(
    main_records: "list[RunRecord]",
    baseline_records: "list[RunRecord]",
    output_dir: Path,
) -> Path:
    """绘制端到端延迟分布直方图（主图 vs Baseline 对比）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    figures_dir = _ensure_output_dir(output_dir)

    main_lat = [r.total_latency_ms for r in main_records if r.success and r.total_latency_ms > 0]
    base_lat = [r.total_latency_ms for r in baseline_records if r.success and r.total_latency_ms > 0]

    fig, ax = plt.subplots(figsize=(9, 5))

    bins = 40
    if main_lat:
        ax.hist(main_lat, bins=bins, alpha=0.6, label=f"Main (n={len(main_lat)})", color="#4C72B0")
        p95_main = float(np.percentile(main_lat, 95))
        ax.axvline(p95_main, color="#4C72B0", linestyle="--", linewidth=1.5, label=f"Main P95={p95_main:.0f}ms")
    if base_lat:
        ax.hist(base_lat, bins=bins, alpha=0.6, label=f"Baseline (n={len(base_lat)})", color="#DD8452")
        p95_base = float(np.percentile(base_lat, 95))
        ax.axvline(p95_base, color="#DD8452", linestyle="--", linewidth=1.5, label=f"Baseline P95={p95_base:.0f}ms")

    ax.axvline(8000, color="red", linestyle=":", linewidth=1.5, label="Target 8000ms")
    ax.set_xlabel("End-to-End Latency (ms)", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.set_title("Latency Distribution — Main vs Baseline", fontsize=12)
    ax.legend(fontsize=9)
    plt.tight_layout()

    path = figures_dir / "latency_distribution_histogram.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


# ── 4. 成本对比柱状图 ─────────────────────────────────────────────────────


def plot_cost_comparison_bar(
    cost: "CostComparison",
    output_dir: Path,
) -> Path:
    """绘制 Token 消耗和费用对比柱状图。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures_dir = _ensure_output_dir(output_dir)

    categories = ["Total Tokens", "LLM Calls", "Est. Cost (CNY)"]
    main_vals = [
        cost.main.total_tokens,
        cost.main.total_llm_calls,
        cost.main.estimated_cost_cny,
    ]
    base_vals = [
        cost.baseline.total_tokens,
        cost.baseline.total_llm_calls,
        cost.baseline.estimated_cost_cny,
    ]

    x = range(len(categories))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 5))

    bars_main = ax.bar([i - width / 2 for i in x], main_vals, width, label="Main (Routed)", color="#4C72B0")
    bars_base = ax.bar([i + width / 2 for i in x], base_vals, width, label="Baseline (All Skills)", color="#DD8452")

    ax.set_xticks(list(x))
    ax.set_xticklabels(categories, fontsize=11)
    ax.set_title(
        f"Cost Comparison — Main vs Baseline\n"
        f"Token Reduction: {cost.token_reduction_pct * 100:.1f}%  "
        f"Cost Saved: {cost.cost_saved_pct * 100:.1f}%",
        fontsize=11,
    )
    ax.legend(fontsize=10)

    for bar in bars_main:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h * 1.01, f"{h:.0f}", ha="center", va="bottom", fontsize=8)
    for bar in bars_base:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h * 1.01, f"{h:.0f}", ha="center", va="bottom", fontsize=8)

    plt.tight_layout()
    path = figures_dir / "cost_comparison_bar.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


# ── 5. 五维雷达图 ─────────────────────────────────────────────────────────


def plot_five_dim_radar(
    clf_metrics: "ClassificationMetrics",
    routing_metrics: "RoutingMetrics",
    main_latency: "LatencyMetrics",
    cost: "CostComparison",
    baseline_latency: "LatencyMetrics | None" = None,
    output_dir: Path | None = None,
) -> Path:
    """绘制五维雷达图，对比主图与 Baseline。

    五个维度（均为 0~1，越大越好）：
    1. 分类准确率：joint_accuracy
    2. Skill 路由 F1：macro_f1
    3. 低 Over-invocation：1 - over_invocation_rate
    4. 低延迟：1 - P95/ref_P95（ref=max(main_P95, baseline_P95)）
    5. 低成本：1 - main_tokens/baseline_tokens

    Args:
        clf_metrics: 分类指标（主图）。
        routing_metrics: 路由指标（主图）。
        main_latency: 主图延迟指标。
        cost: 成本对比。
        baseline_latency: Baseline 延迟指标（用于归一化延迟轴）。
        output_dir: PNG 输出目录。

    Returns:
        输出文件路径。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    if output_dir is None:
        output_dir = Path("evaluation/reports")
    figures_dir = _ensure_output_dir(output_dir)

    # ── 计算各维度值 ──────────────────────────────────────────────────
    ref_p95 = max(
        main_latency.p95_ms,
        baseline_latency.p95_ms if baseline_latency else main_latency.p95_ms,
    )
    latency_score_main = 1.0 - (main_latency.p95_ms / ref_p95) if ref_p95 > 0 else 1.0
    latency_score_base = (
        1.0 - (baseline_latency.p95_ms / ref_p95)
        if (baseline_latency and ref_p95 > 0)
        else 0.0
    )

    ref_tokens = max(cost.main.total_tokens, cost.baseline.total_tokens)
    cost_score_main = 1.0 - (cost.main.total_tokens / ref_tokens) if ref_tokens > 0 else 1.0
    cost_score_base = 1.0 - (cost.baseline.total_tokens / ref_tokens) if ref_tokens > 0 else 0.0

    dims = ["分类准确率", "路由 F1", "低 Over-inv", "低延迟 P95", "低成本"]

    main_vals = [
        clf_metrics.joint_accuracy,
        routing_metrics.macro_f1,
        1.0 - routing_metrics.over_invocation_rate,
        latency_score_main,
        cost_score_main,
    ]
    # Baseline：分类准确率与路由指标暂以主图值填充（baseline 路由无意义），
    # over_invocation=1.0（全选必然全 over-invoke），延迟和成本用 baseline 值。
    base_vals = [
        clf_metrics.joint_accuracy,  # baseline 分类同主图
        0.0,                          # baseline 路由 F1 无意义（全选）
        0.0,                          # over_invocation_rate=1.0 → 1-1=0
        latency_score_base,
        cost_score_base,
    ]

    # ── 绘图 ──────────────────────────────────────────────────────────
    angles = np.linspace(0, 2 * np.pi, len(dims), endpoint=False).tolist()
    angles += angles[:1]  # 闭合

    main_vals_plot = main_vals + main_vals[:1]
    base_vals_plot = base_vals + base_vals[:1]

    fig, ax = plt.subplots(figsize=(7, 7), subplot_kw={"polar": True})

    ax.plot(angles, main_vals_plot, "o-", linewidth=2, color="#4C72B0", label="Main (Routed)")
    ax.fill(angles, main_vals_plot, alpha=0.25, color="#4C72B0")

    ax.plot(angles, base_vals_plot, "s--", linewidth=2, color="#DD8452", label="Baseline (All Skills)")
    ax.fill(angles, base_vals_plot, alpha=0.15, color="#DD8452")

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dims, fontsize=12, fontweight="bold")
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], fontsize=8)
    ax.set_title("场景 A 综合评估雷达图\nScenario A — Five-Dimension Radar", fontsize=13, pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=10)

    # 标注主图各点数值
    for angle, val, dim in zip(angles[:-1], main_vals, dims):
        ax.annotate(
            f"{val:.2f}",
            xy=(angle, val),
            fontsize=8,
            ha="center",
            va="bottom",
            color="#2c5f8e",
        )

    plt.tight_layout()
    path = figures_dir / "five_dim_radar.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def generate_all_plots(
    clf_metrics: "ClassificationMetrics",
    routing_metrics: "RoutingMetrics",
    main_latency: "LatencyMetrics",
    baseline_latency: "LatencyMetrics",
    cost: "CostComparison",
    main_records: "list[RunRecord]",
    baseline_records: "list[RunRecord]",
    output_dir: Path,
) -> dict[str, list[Path] | Path]:
    """一键生成所有 5 类图表。

    Returns:
        dict，key 为图表类型，value 为路径（混淆矩阵为列表，其余为单个路径）。
    """
    return {
        "confusion_matrices": plot_confusion_matrices(clf_metrics, output_dir),
        "routing_f1_bar": plot_routing_f1_bar(routing_metrics, output_dir),
        "latency_histogram": plot_latency_histogram(main_records, baseline_records, output_dir),
        "cost_comparison_bar": plot_cost_comparison_bar(cost, output_dir),
        "five_dim_radar": plot_five_dim_radar(
            clf_metrics,
            routing_metrics,
            main_latency,
            cost,
            baseline_latency=baseline_latency,
            output_dir=output_dir,
        ),
    }
