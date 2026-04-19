"""test_classification_metrics.py — 分类指标单元测试。

使用 20 条手工构造的 RunRecord，对照手动计算的期望值验证结果。
"""

from __future__ import annotations

import pytest

from jobpilot_agent.evaluation.metrics.classification import compute_classification_metrics
from tests.evaluation.conftest import make_record


def _make_dataset():
    """构造 20 条已知结果的记录：
    - 16 条全字段正确
    - 4 条 job_type 错误（tech 预测为 product）
    - joint_accuracy = 16/20 = 0.80
    """
    records = []
    for i in range(16):
        records.append(make_record(
            jd_id=f"correct_{i}",
            predicted_job_type="tech",
            true_job_type="tech",
        ))
    for i in range(4):
        records.append(make_record(
            jd_id=f"wrong_{i}",
            predicted_job_type="product",
            true_job_type="tech",
        ))
    return records


def test_joint_accuracy():
    """16/20 条全对 → joint_accuracy = 0.80。"""
    records = _make_dataset()
    metrics = compute_classification_metrics(records)
    assert abs(metrics.joint_accuracy - 0.80) < 1e-6, (
        f"Expected joint_accuracy=0.80, got {metrics.joint_accuracy}"
    )


def test_evaluated_count():
    """所有 20 条成功 → evaluated_count = 20。"""
    records = _make_dataset()
    metrics = compute_classification_metrics(records)
    assert metrics.evaluated_count == 20


def test_job_type_accuracy_with_errors():
    """4 条 job_type 错，job_type accuracy = 16/20 = 0.80。"""
    records = _make_dataset()
    metrics = compute_classification_metrics(records)
    fm = metrics.per_field["job_type"]
    assert abs(fm.accuracy - 0.80) < 1e-6


def test_all_correct_joint_accuracy():
    """全部正确时 joint_accuracy = 1.0。"""
    records = [make_record(jd_id=f"all_correct_{i}") for i in range(10)]
    metrics = compute_classification_metrics(records)
    assert abs(metrics.joint_accuracy - 1.0) < 1e-6


def test_all_correct_field_accuracy():
    """全部正确时每个字段 accuracy = 1.0。"""
    records = [make_record(jd_id=f"c_{i}") for i in range(10)]
    metrics = compute_classification_metrics(records)
    for field in ["job_type", "level", "locale", "channel"]:
        fm = metrics.per_field.get(field)
        assert fm is not None, f"Missing field metrics for {field}"
        assert abs(fm.accuracy - 1.0) < 1e-6, f"{field} accuracy={fm.accuracy}"


def test_confusion_matrix_shape():
    """混淆矩阵形状与标签数量一致。"""
    records = _make_dataset()
    metrics = compute_classification_metrics(records)
    fm = metrics.per_field["job_type"]
    n = len(fm.labels_order)
    assert len(fm.confusion_matrix) == n
    assert all(len(row) == n for row in fm.confusion_matrix)


def test_failed_records_excluded():
    """success=False 的记录不计入指标。"""
    records = [make_record(jd_id=f"ok_{i}") for i in range(10)]
    records += [make_record(jd_id=f"fail_{i}", success=False) for i in range(5)]
    metrics = compute_classification_metrics(records)
    assert metrics.evaluated_count == 10


def test_raises_on_all_failed():
    """所有记录失败时应抛出 ValueError。"""
    records = [make_record(jd_id=f"fail_{i}", success=False) for i in range(5)]
    with pytest.raises(ValueError, match="没有有效"):
        compute_classification_metrics(records)


def test_per_field_has_all_five_fields():
    """per_field 包含全部 5 个分类字段。"""
    records = [make_record(jd_id=f"r_{i}") for i in range(10)]
    metrics = compute_classification_metrics(records)
    for field in ["job_type", "sub_type", "level", "locale", "channel"]:
        assert field in metrics.per_field


def test_macro_f1_perfect():
    """全部正确时 macro_f1 = 1.0。"""
    records = [make_record(jd_id=f"r_{i}") for i in range(10)]
    metrics = compute_classification_metrics(records)
    fm = metrics.per_field["job_type"]
    assert abs(fm.macro_f1 - 1.0) < 1e-6
