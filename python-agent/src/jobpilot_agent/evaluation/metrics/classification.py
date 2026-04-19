"""JD 分类指标计算。

五维分类字段：job_type / sub_type / level / locale / channel
对每个字段独立计算 accuracy / precision / recall / F1，
同时计算五维联合准确率（joint_accuracy：所有字段全对才算对）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from jobpilot_agent.evaluation.runners.scenario_a_runner import RunRecord

_CLASSIFICATION_FIELDS = ["job_type", "sub_type", "level", "locale", "channel"]


class FieldMetrics(BaseModel):
    """单个分类字段的指标。

    Attributes:
        accuracy: 整体准确率。
        macro_f1: 宏平均 F1。
        weighted_f1: 加权平均 F1。
        precision_per_class: 各类别精确率。
        recall_per_class: 各类别召回率。
        f1_per_class: 各类别 F1。
        confusion_matrix: 混淆矩阵（行=真实，列=预测）。
        labels_order: 混淆矩阵的标签顺序。
        support_per_class: 各类别样本数。
    """

    accuracy: float
    macro_f1: float
    weighted_f1: float
    precision_per_class: dict[str, float]
    recall_per_class: dict[str, float]
    f1_per_class: dict[str, float]
    confusion_matrix: list[list[int]]
    labels_order: list[str]
    support_per_class: dict[str, int]


class ClassificationMetrics(BaseModel):
    """所有分类字段的综合指标。

    Attributes:
        joint_accuracy: 五维全对才算对的联合准确率。
        evaluated_count: 参与计算的有效样本数（排除预测失败的）。
        per_field: 各字段独立指标。
    """

    joint_accuracy: float
    evaluated_count: int
    per_field: dict[str, FieldMetrics]


def compute_classification_metrics(records: list[RunRecord]) -> ClassificationMetrics:
    """使用 sklearn 计算分类指标。

    只使用 success=True 且 predicted_classification 非空的记录。

    Args:
        records: RunRecord 列表。

    Returns:
        ClassificationMetrics 实例。
    """
    from sklearn.metrics import (  # type: ignore[import]
        accuracy_score,
        classification_report,
        confusion_matrix,
    )

    # 过滤有效记录
    valid = [r for r in records if r.success and r.predicted_classification]
    if not valid:
        raise ValueError("没有有效的分类预测记录（success=True 且 predicted_classification 非空）")

    evaluated_count = len(valid)

    # ── 五维联合准确率 ─────────────────────────────────────────────
    joint_correct = 0
    for rec in valid:
        all_correct = all(
            rec.predicted_classification.get(field) == rec.ground_truth_labels.get(field)
            for field in _CLASSIFICATION_FIELDS
        )
        if all_correct:
            joint_correct += 1
    joint_accuracy = joint_correct / evaluated_count

    # ── 各字段独立指标 ─────────────────────────────────────────────
    per_field: dict[str, FieldMetrics] = {}

    for field in _CLASSIFICATION_FIELDS:
        y_true = [str(r.ground_truth_labels.get(field) or "") for r in valid]
        y_pred = [str(r.predicted_classification.get(field) or "") for r in valid]

        labels = sorted(set(y_true) | set(y_pred))
        if not labels:
            continue

        acc = float(accuracy_score(y_true, y_pred))
        cm = confusion_matrix(y_true, y_pred, labels=labels).tolist()

        report: dict[str, Any] = classification_report(
            y_true, y_pred,
            labels=labels,
            output_dict=True,
            zero_division=0,
        )

        precision_per_class: dict[str, float] = {}
        recall_per_class: dict[str, float] = {}
        f1_per_class: dict[str, float] = {}
        support_per_class: dict[str, int] = {}

        for lbl in labels:
            lbl_report = report.get(lbl) or {}
            precision_per_class[lbl] = float(lbl_report.get("precision") or 0)
            recall_per_class[lbl] = float(lbl_report.get("recall") or 0)
            f1_per_class[lbl] = float(lbl_report.get("f1-score") or 0)
            support_per_class[lbl] = int(lbl_report.get("support") or 0)

        per_field[field] = FieldMetrics(
            accuracy=acc,
            macro_f1=float(report.get("macro avg", {}).get("f1-score") or 0),
            weighted_f1=float(report.get("weighted avg", {}).get("f1-score") or 0),
            precision_per_class=precision_per_class,
            recall_per_class=recall_per_class,
            f1_per_class=f1_per_class,
            confusion_matrix=cm,
            labels_order=labels,
            support_per_class=support_per_class,
        )

    return ClassificationMetrics(
        joint_accuracy=joint_accuracy,
        evaluated_count=evaluated_count,
        per_field=per_field,
    )
