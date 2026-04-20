"""RAGAS 评估报告生成器。

产出：
- evaluation/reports/ragas_v1.md（6 章 Markdown 报告）
- evaluation/reports/figures/ragas_distribution.png（四指标分布直方图）
- evaluation/reports/figures/ragas_per_company_bar.png（Top10 公司柱状图）
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jobpilot_agent.evaluation.ragas.metrics_wrapper import aggregate_results, safe_float
from jobpilot_agent.evaluation.ragas.schema import RagasAggregate, RagasExample, RagasResult

_TARGETS = {
    "context_relevancy": 0.75,
    "context_recall": 0.80,
    "faithfulness": 0.85,
    "answer_relevancy": 0.80,
}

_METRIC_LABELS = {
    "context_relevancy": "Context Relevance",
    "context_recall": "Context Recall",
    "faithfulness": "Faithfulness",
    "answer_relevancy": "Answer Relevancy",
}


def _status(val: float, target: float) -> str:
    return "✅" if val >= target else "❌"


def _render_report(
    agg: RagasAggregate,
    results: list[RagasResult],
    examples: list[RagasExample],
    figures_dir: Path,
    judge_llm: str = "deepseek-chat",
    embedder: str = "bge-m3",
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    human_count = sum(1 for e in examples if e.ground_truth_source == "human")
    llm_count = sum(1 for e in examples if e.ground_truth_source == "llm_assisted")

    cr = agg.mean_context_relevancy
    cre = agg.mean_context_recall
    fai = agg.mean_faithfulness
    ar = agg.mean_answer_relevancy

    # 找失败案例：faithfulness 最低的 3 条
    failed = sorted(
        [r for r in results if r.error is None],
        key=lambda r: safe_float(r.faithfulness),
    )[:3]
    example_map = {e.example_id: e for e in examples}

    lines = [
        "# RAGAS 检索质量评估报告 v1",
        "",
        f"**执行时间**：{ts}  ",
        f"**评估集**：{agg.total} 条（{human_count} 人工标注 + {llm_count} LLM 辅助）  ",
        f"**Judge LLM**：{judge_llm}  ",
        f"**Embedder**：{embedder}  ",
        "",
        "## 1. 摘要",
        "",
        "| 指标 | 均值 | 目标值 | 达成 |",
        "|---|---|---|---|",
        f"| Context Relevance | {cr:.3f} | > {_TARGETS['context_relevancy']} | {_status(cr, _TARGETS['context_relevancy'])} |",
        f"| Context Recall | {cre:.3f} | > {_TARGETS['context_recall']} | {_status(cre, _TARGETS['context_recall'])} |",
        f"| Faithfulness | {fai:.3f} | > {_TARGETS['faithfulness']} | {_status(fai, _TARGETS['faithfulness'])} |",
        f"| Answer Relevancy | {ar:.3f} | > {_TARGETS['answer_relevancy']} | {_status(ar, _TARGETS['answer_relevancy'])} |",
        "",
        f"**成功率**：{agg.successful}/{agg.total} ({agg.successful/agg.total*100:.1f}%)",
        "",
        "## 2. 各指标分布",
        "",
    ]

    dist_path = figures_dir / "ragas_distribution.png"
    if dist_path.exists():
        lines += [f"![指标分布](figures/ragas_distribution.png)", ""]
    else:
        lines += ["*(运行 render 命令后生成图表)*", ""]

    # Top 10 公司
    lines += ["## 3. 分公司表现（Top 10）", ""]
    top_companies = sorted(
        agg.by_company.items(),
        key=lambda kv: kv[1].count,
        reverse=True,
    )[:10]

    lines += ["| 公司 | 数量 | CR | CRE | FAI | AR |", "|---|---|---|---|---|---|"]
    for company, m in top_companies:
        lines.append(
            f"| {company} | {m.count} | "
            f"{m.mean_context_relevancy:.3f} | {m.mean_context_recall:.3f} | "
            f"{m.mean_faithfulness:.3f} | {m.mean_answer_relevancy:.3f} |"
        )

    bar_path = figures_dir / "ragas_per_company_bar.png"
    if bar_path.exists():
        lines += ["", f"![公司对比](figures/ragas_per_company_bar.png)"]
    lines.append("")

    # 分 job_type
    lines += ["## 4. 分岗位类型表现", ""]
    lines += ["| Job Type | 数量 | CR | CRE | FAI | AR |", "|---|---|---|---|---|---|"]
    for jt, m in sorted(agg.by_job_type.items()):
        lines.append(
            f"| {jt} | {m.count} | "
            f"{m.mean_context_relevancy:.3f} | {m.mean_context_recall:.3f} | "
            f"{m.mean_faithfulness:.3f} | {m.mean_answer_relevancy:.3f} |"
        )
    lines.append("")

    # 失败案例分析
    lines += ["## 5. 失败案例分析", ""]
    for idx, r in enumerate(failed, 1):
        ex = example_map.get(r.example_id)
        lines += [
            f"### 案例 {idx}：Faithfulness = {safe_float(r.faithfulness):.3f}",
            "",
            f"- **Question**：{ex.question if ex else '(unknown)'}",
            f"- **Company / Position**：{ex.company if ex else '?'} / {ex.position if ex else '?'}",
            f"- **CR / CRE / AR**：{safe_float(r.context_relevancy):.3f} / "
            f"{safe_float(r.context_recall):.3f} / {safe_float(r.answer_relevancy):.3f}",
            "- **归因**：LLM 合成时可能引入了 context 未覆盖的内容，建议在 final_synthesis prompt 中"
            "加强 faithfulness 约束（禁止引用 context 未提及的数字/名词）",
            "",
        ]

    # 结论
    all_pass = all([
        cr >= _TARGETS["context_relevancy"],
        cre >= _TARGETS["context_recall"],
        fai >= _TARGETS["faithfulness"],
        ar >= _TARGETS["answer_relevancy"],
    ])
    conclusion = "四项指标全部达标 ✅" if all_pass else "部分指标未达标，详见第 5 章失败案例分析"

    lines += [
        "## 6. 结论与改进方向",
        "",
        f"**总体结论**：{conclusion}",
        "",
        "**指标解读**：",
        f"- CR={cr:.3f}：RAG 检索到的面经与岗位问题相关性",
        f"- CRE={cre:.3f}：ground_truth 中所需信息在 context 中的覆盖率",
        f"- FAI={fai:.3f}：最终答案对 context 的忠实度（幻觉率越低越好）",
        f"- AR={ar:.3f}：答案对原始问题的针对性",
        "",
        "**改进方向**：",
        "- 若 Faithfulness 偏低：在 `final_synthesis` prompt 中追加「不得引用 context 未提及的数字/术语」约束",
        "- 若 Context Recall 偏低：增大 `interview_rag` 的 `top_k`（当前 tech_qa=8, project=5），或扩充面经库",
        "- 若 Context Relevance 偏低：优化 BM25 权重或开启 cross-encoder rerank",
    ]

    return "\n".join(lines) + "\n"


def plot_ragas_distribution(results: list[RagasResult], figures_dir: Path) -> Path:
    """四指标分布直方图（4 subplot）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figures_dir.mkdir(parents=True, exist_ok=True)
    successful = [r for r in results if r.error is None]
    metrics = {
        "Context Relevance": [safe_float(r.context_relevancy) for r in successful],
        "Context Recall": [safe_float(r.context_recall) for r in successful],
        "Faithfulness": [safe_float(r.faithfulness) for r in successful],
        "Answer Relevancy": [safe_float(r.answer_relevancy) for r in successful],
    }
    targets = [0.75, 0.80, 0.85, 0.80]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52"]

    for ax, (name, vals), target, color in zip(axes.flat, metrics.items(), targets, colors):
        ax.hist(vals, bins=20, color=color, alpha=0.75, edgecolor="white")
        ax.axvline(target, color="red", linestyle="--", linewidth=1.5, label=f"Target={target}")
        if vals:
            mean_val = sum(vals) / len(vals)
            ax.axvline(mean_val, color="black", linestyle="-", linewidth=1.2, label=f"Mean={mean_val:.3f}")
        ax.set_title(name, fontsize=12, fontweight="bold")
        ax.set_xlabel("Score", fontsize=10)
        ax.set_ylabel("Count", fontsize=10)
        ax.set_xlim(0, 1.05)
        ax.legend(fontsize=8)

    fig.suptitle("RAGAS 四项指标分布", fontsize=14, fontweight="bold")
    plt.tight_layout()

    path = figures_dir / "ragas_distribution.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_company_bar(agg: RagasAggregate, figures_dir: Path) -> Path:
    """Top 10 公司四指标分组柱状图。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    figures_dir.mkdir(parents=True, exist_ok=True)
    top = sorted(agg.by_company.items(), key=lambda kv: kv[1].count, reverse=True)[:10]
    if not top:
        # 空图
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.text(0.5, 0.5, "No company data", ha="center", va="center")
        path = figures_dir / "ragas_per_company_bar.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        return path

    companies = [c for c, _ in top]
    cr_vals = [m.mean_context_relevancy for _, m in top]
    cre_vals = [m.mean_context_recall for _, m in top]
    fai_vals = [m.mean_faithfulness for _, m in top]
    ar_vals = [m.mean_answer_relevancy for _, m in top]

    x = np.arange(len(companies))
    width = 0.2

    fig, ax = plt.subplots(figsize=(max(10, len(companies) * 1.2), 6))
    ax.bar(x - 1.5 * width, cr_vals, width, label="Context Relevance", color="#4C72B0")
    ax.bar(x - 0.5 * width, cre_vals, width, label="Context Recall", color="#DD8452")
    ax.bar(x + 0.5 * width, fai_vals, width, label="Faithfulness", color="#55A868")
    ax.bar(x + 1.5 * width, ar_vals, width, label="Answer Relevancy", color="#C44E52")

    ax.set_xticks(x)
    ax.set_xticklabels(companies, rotation=30, ha="right", fontsize=9)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Score", fontsize=11)
    ax.set_title("RAGAS 四项指标 — Top 10 公司对比", fontsize=13, fontweight="bold")
    ax.legend(fontsize=9)
    ax.axhline(0.8, color="red", linestyle="--", linewidth=0.8, label="Target 0.80")
    plt.tight_layout()

    path = figures_dir / "ragas_per_company_bar.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return path


def render(
    examples: list[RagasExample],
    results: list[RagasResult],
    output_path: str,
    judge_llm: str = "deepseek-chat",
    embedder: str = "bge-m3",
) -> RagasAggregate:
    """一键生成 Markdown 报告 + 两张 PNG。

    Returns:
        RagasAggregate — 聚合结果（供调用方打印/断言）。
    """
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    figures_dir = output_path_obj.parent / "figures"

    agg = aggregate_results(results, examples)

    # 生成图表
    plot_ragas_distribution(results, figures_dir)
    plot_company_bar(agg, figures_dir)

    # 生成 Markdown
    md = _render_report(agg, results, examples, figures_dir, judge_llm=judge_llm, embedder=embedder)
    output_path_obj.write_text(md, encoding="utf-8")

    return agg
