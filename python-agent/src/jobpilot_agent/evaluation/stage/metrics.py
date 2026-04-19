"""阶段预测指标计算。"""

from __future__ import annotations

from pydantic import BaseModel, Field

_STAGE_LABELS = [
    "intro",
    "project_deep_dive",
    "tech_qa",
    "scenario",
    "reverse",
    "closing",
]


class StageEvalResult(BaseModel):
    total_samples: int
    accuracy: float
    per_stage_precision: dict[str, float] = Field(default_factory=dict)
    per_stage_recall: dict[str, float] = Field(default_factory=dict)
    per_stage_f1: dict[str, float] = Field(default_factory=dict)
    confusion_matrix: list[list[int]] = Field(default_factory=list)
    labels_order: list[str] = Field(default_factory=list)


def compute_metrics(
    true_labels: list[str],
    pred_labels: list[str],
    labels: list[str] | None = None,
) -> StageEvalResult:
    """从 true/pred 列表计算 accuracy、per-stage P/R/F1、confusion matrix。"""
    if labels is None:
        labels = _STAGE_LABELS
    n = len(true_labels)
    if n == 0:
        return StageEvalResult(total_samples=0, accuracy=0.0, labels_order=labels)

    label_idx = {lbl: i for i, lbl in enumerate(labels)}
    k = len(labels)

    # confusion matrix: cm[true][pred]
    cm: list[list[int]] = [[0] * k for _ in range(k)]
    correct = 0
    for t, p in zip(true_labels, pred_labels):
        ti = label_idx.get(t, -1)
        pi = label_idx.get(p, -1)
        if ti >= 0 and pi >= 0:
            cm[ti][pi] += 1
        if t == p:
            correct += 1

    accuracy = correct / n

    per_stage_precision: dict[str, float] = {}
    per_stage_recall: dict[str, float] = {}
    per_stage_f1: dict[str, float] = {}

    for i, lbl in enumerate(labels):
        tp = cm[i][i]
        fp = sum(cm[r][i] for r in range(k)) - tp
        fn = sum(cm[i][c] for c in range(k)) - tp

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        per_stage_precision[lbl] = round(precision, 4)
        per_stage_recall[lbl] = round(recall, 4)
        per_stage_f1[lbl] = round(f1, 4)

    return StageEvalResult(
        total_samples=n,
        accuracy=round(accuracy, 4),
        per_stage_precision=per_stage_precision,
        per_stage_recall=per_stage_recall,
        per_stage_f1=per_stage_f1,
        confusion_matrix=cm,
        labels_order=labels,
    )
