"""Unit tests for stage evaluation metrics (no LLM required)."""

from __future__ import annotations

import pytest

from jobpilot_agent.evaluation.stage.metrics import (
    _STAGE_LABELS,
    compute_metrics,
)

_LABELS = _STAGE_LABELS


def test_perfect_accuracy() -> None:
    true = ["intro", "tech_qa", "closing", "scenario"]
    pred = ["intro", "tech_qa", "closing", "scenario"]
    result = compute_metrics(true, pred, _LABELS)
    assert result.accuracy == 1.0
    assert result.total_samples == 4
    for lbl in ["intro", "tech_qa", "closing", "scenario"]:
        assert result.per_stage_f1[lbl] == 1.0


def test_zero_accuracy() -> None:
    true = ["intro", "intro", "intro"]
    pred = ["tech_qa", "tech_qa", "tech_qa"]
    result = compute_metrics(true, pred, _LABELS)
    assert result.accuracy == 0.0
    assert result.per_stage_f1["intro"] == 0.0
    assert result.per_stage_f1["tech_qa"] == 0.0


def test_confusion_matrix_dimensions() -> None:
    true = ["intro", "tech_qa"]
    pred = ["tech_qa", "intro"]
    result = compute_metrics(true, pred, _LABELS)
    assert len(result.confusion_matrix) == len(_LABELS)
    assert all(len(row) == len(_LABELS) for row in result.confusion_matrix)


def test_confusion_matrix_values() -> None:
    # true=intro pred=tech_qa → cm[intro_idx][tech_qa_idx] = 1
    true = ["intro", "intro", "tech_qa"]
    pred = ["intro", "tech_qa", "tech_qa"]
    result = compute_metrics(true, pred, _LABELS)
    intro_i = _LABELS.index("intro")
    tech_i = _LABELS.index("tech_qa")
    assert result.confusion_matrix[intro_i][intro_i] == 1
    assert result.confusion_matrix[intro_i][tech_i] == 1
    assert result.confusion_matrix[tech_i][tech_i] == 1


def test_per_stage_precision_recall_f1() -> None:
    # intro: 2 true, 1 predicted correctly → recall=0.5; 1 tp, 0 fp → precision=1.0
    true = ["intro", "intro", "tech_qa"]
    pred = ["intro", "tech_qa", "tech_qa"]
    result = compute_metrics(true, pred, _LABELS)
    assert result.per_stage_precision["intro"] == 1.0
    assert result.per_stage_recall["intro"] == pytest.approx(0.5, abs=1e-4)
    assert result.per_stage_f1["intro"] == pytest.approx(2 / 3, abs=1e-3)


def test_labels_order_contains_all_stages() -> None:
    result = compute_metrics(["intro"], ["intro"])
    assert set(result.labels_order) == set(_LABELS)
    assert len(result.labels_order) == 6


def test_empty_input() -> None:
    result = compute_metrics([], [])
    assert result.total_samples == 0
    assert result.accuracy == 0.0


def test_unknown_label_does_not_crash() -> None:
    # unknown labels: not in confusion matrix but accuracy still counts equality
    true = ["unknown_stage", "intro"]
    pred = ["unknown_stage", "intro"]
    result = compute_metrics(true, pred, _LABELS)
    assert result.accuracy == 1.0  # both equal → correct
    assert result.total_samples == 2
