"""阶段预测评估报告生成。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jobpilot_agent.evaluation.stage.metrics import StageEvalResult
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

_TARGET_ACCURACY = 0.85


def _check(value: float, target: float) -> str:
    return "✅" if value >= target else "❌"


def generate_confusion_matrix_plot(
    result: StageEvalResult,
    output_dir: Path,
) -> Path | None:
    """生成混淆矩阵 PNG，返回文件路径；无 matplotlib 时返回 None。"""
    try:
        import matplotlib  # type: ignore[import-not-found]

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore[import-not-found]
        import numpy as np
    except ImportError:
        log.warning("renderer.matplotlib_not_installed")
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    labels = result.labels_order
    cm = np.array(result.confusion_matrix, dtype=float)

    # 行归一化（recall-oriented）
    row_sums = cm.sum(axis=1, keepdims=True)
    cm_norm = np.divide(cm, row_sums, where=row_sums != 0)

    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(cm_norm, interpolation="nearest", cmap="Blues", vmin=0, vmax=1)
    plt.colorbar(im, ax=ax)

    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=9)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Predicted Stage")
    ax.set_ylabel("True Stage")
    ax.set_title(f"Stage Prediction Confusion Matrix (Accuracy={result.accuracy:.3f})")

    # 在格子里写数值
    raw_cm = result.confusion_matrix
    for i in range(len(labels)):
        for j in range(len(labels)):
            count = raw_cm[i][j]
            ax.text(
                j, i, str(count),
                ha="center", va="center",
                color="white" if cm_norm[i][j] > 0.5 else "black",
                fontsize=8,
            )

    fig.tight_layout()
    out_path = output_dir / "stage_confusion_matrix.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    log.info("renderer.confusion_matrix_saved", path=str(out_path))
    return out_path


def generate_report(
    result: StageEvalResult,
    output_path: Path,
    model_name: str = "deepseek-chat",
    figures: dict[str, Path] | None = None,
) -> str:
    """生成 Markdown 评估报告。"""
    if figures is None:
        figures = {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    labels = result.labels_order

    lines = [
        "# 阶段推进准确率评估报告 v1",
        "",
        f"**执行时间**：{now}",
        f"**模型**：{model_name}",
        f"**总样本数**：{result.total_samples}",
        "",
        "---",
        "",
        "## 摘要",
        "",
        "| 指标 | 本项目 | 目标 | 达成 |",
        "|---|---|---|---|",
        f"| Accuracy | {result.accuracy:.4f} | > {_TARGET_ACCURACY} |"
        f" {_check(result.accuracy, _TARGET_ACCURACY)} |",
        "",
        "---",
        "",
        "## 1. 混淆矩阵",
        "",
    ]

    if "confusion_matrix" in figures:
        rel = figures["confusion_matrix"].name
        lines.append(f"![混淆矩阵](figures/{rel})")
        lines.append("")

    # 文字混淆矩阵（ASCII）
    header = "| True \\ Pred | " + " | ".join(labels) + " |"
    sep = "|---|" + "---|" * len(labels)
    lines += [header, sep]
    for i, lbl in enumerate(labels):
        row_vals = " | ".join(str(result.confusion_matrix[i][j]) for j in range(len(labels)))
        lines.append(f"| **{lbl}** | {row_vals} |")
    lines.append("")

    lines += [
        "---",
        "",
        "## 2. 分阶段指标",
        "",
        "| Stage | Precision | Recall | F1 |",
        "|---|---|---|---|",
    ]
    for lbl in labels:
        p = result.per_stage_precision.get(lbl, 0)
        r = result.per_stage_recall.get(lbl, 0)
        f = result.per_stage_f1.get(lbl, 0)
        lines.append(f"| {lbl} | {p:.4f} | {r:.4f} | {f:.4f} |")
    lines.append("")

    # Top 混淆对
    confusion_pairs: list[tuple[float, str, str]] = []
    for i, true_lbl in enumerate(labels):
        for j, pred_lbl in enumerate(labels):
            if i != j and result.confusion_matrix[i][j] > 0:
                row_sum = sum(result.confusion_matrix[i])
                rate = result.confusion_matrix[i][j] / row_sum if row_sum > 0 else 0.0
                confusion_pairs.append((rate, true_lbl, pred_lbl))
    confusion_pairs.sort(reverse=True)

    lines += [
        "---",
        "",
        "## 3. Top 5 易混淆阶段对",
        "",
        "| True → Pred | 混淆率 |",
        "|---|---|",
    ]
    for rate, t, pred_lbl_str in confusion_pairs[:5]:
        lines.append(f"| {t} → {pred_lbl_str} | {rate:.1%} |")
    lines.append("")

    lines += [
        "---",
        "",
        "## 4. 失败归因分析",
        "",
    ]
    weak_stages = [
        lbl for lbl in labels
        if result.per_stage_f1.get(lbl, 1.0) < 0.7
    ]
    if weak_stages:
        for lbl in weak_stages:
            lines += [
                f"**{lbl}**（F1={result.per_stage_f1.get(lbl, 0):.4f}）：",
                "- 该阶段的对话特征与相邻阶段高度相似，建议在 prompt 中补充更清晰的阶段边界描述。",
                "",
            ]
    else:
        lines += ["所有阶段 F1 ≥ 0.70，整体表现良好。", ""]

    lines += [
        "---",
        "",
        "## 5. 改进建议",
        "",
        "1. **强化边界阶段描述**：`project_deep_dive` 与 `tech_qa` 内容相似，"
        "可在 predict_stage prompt 中增加区分示例。",
        "2. **扩充训练样本**：`reverse` / `closing` 阶段样本量少，F1 方差大，"
        "可从更多面经中补充这两个阶段的样本。",
        "3. **Few-shot 示例**：在 predict_stage system prompt 中加入 1-2 个 few-shot 对话示例，"
        "提升 `scenario` vs `tech_qa` 的判别准确率。",
        "",
    ]

    report = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    log.info("renderer.report_written", path=str(output_path))
    return report
