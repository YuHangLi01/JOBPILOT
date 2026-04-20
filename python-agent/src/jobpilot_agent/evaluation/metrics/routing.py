"""Skill 路由指标计算（多标签分类）。

评估维度：
- Over-invocation Rate：调用了 forbidden_skills 的比例
- Under-invocation Rate：漏调了 expected_skills 的比例
- Perfect Match Rate：invoked == expected 完全一致的比例
- Per-skill Precision / Recall / F1（多标签意义下）

多标签 TP/FP/FN/TN 定义（对每条记录，针对每个 Skill）：
- TP: skill 在 expected_skills 中，且被 invoke 了
- FP: skill 在 forbidden_skills 中，却被 invoke 了
- FN: skill 在 expected_skills 中，但没被 invoke
- TN: skill 不在 expected_skills 中，也没被 invoke

注：expected_skills 和 forbidden_skills 可能不覆盖所有 Skill，
未出现在两个列表中的 Skill 被视为「不关心」，不计入 FP/TN。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from jobpilot_agent.evaluation.runners.scenario_a_runner import RunRecord


class SkillRoutingMetrics(BaseModel):
    """单个 Skill 的路由指标。

    Attributes:
        precision: TP / (TP + FP)。
        recall: TP / (TP + FN)。
        f1: 2 * precision * recall / (precision + recall)。
        true_positive: 应调且调了。
        false_positive: 不该调却调了（forbidden 中出现）。
        false_negative: 应调却没调。
        true_negative: 不该调且没调（forbidden 中未出现）。
    """

    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int


class RoutingMetrics(BaseModel):
    """Skill 路由综合指标。

    Attributes:
        macro_precision: 所有 Skill 精确率的宏平均。
        macro_recall: 所有 Skill 召回率的宏平均。
        macro_f1: 所有 Skill F1 的宏平均。
        over_invocation_rate: 至少调了 1 个 forbidden Skill 的记录比例。
        under_invocation_rate: 漏调了至少 1 个 expected Skill 的记录比例。
        perfect_match_rate: predicted_invoked == expected_skills 完全相同的比例。
        evaluated_count: 参与计算的有效记录数。
        per_skill: 各 Skill 的独立指标。
    """

    macro_precision: float
    macro_recall: float
    macro_f1: float
    over_invocation_rate: float
    under_invocation_rate: float
    perfect_match_rate: float
    evaluated_count: int
    per_skill: dict[str, SkillRoutingMetrics]


def compute_routing_metrics(
    records: list[RunRecord],
    all_skill_names: list[str] | None = None,
) -> RoutingMetrics:
    """计算 Skill 路由多标签分类指标。

    Args:
        records: RunRecord 列表。
        all_skill_names: 所有 Skill 名称列表（用于 TN 计算）。
            若为 None，从记录中自动收集。

    Returns:
        RoutingMetrics 实例。
    """
    valid = [r for r in records if r.success]
    if not valid:
        raise ValueError("没有有效的路由记录（success=True）")

    evaluated_count = len(valid)

    # ── 收集所有 Skill 名称 ─────────────────────────────────────────
    if all_skill_names is None:
        skill_set: set[str] = set()
        for r in valid:
            skill_set.update(r.ground_truth_expected_skills)
            skill_set.update(r.ground_truth_forbidden_skills)
            skill_set.update(r.predicted_invoked_skills)
        all_skill_names = sorted(skill_set)

    # ── 初始化计数器 ────────────────────────────────────────────────
    tp: dict[str, int] = {s: 0 for s in all_skill_names}
    fp: dict[str, int] = {s: 0 for s in all_skill_names}
    fn: dict[str, int] = {s: 0 for s in all_skill_names}
    tn: dict[str, int] = {s: 0 for s in all_skill_names}

    over_count = 0
    under_count = 0
    perfect_count = 0

    for rec in valid:
        predicted = set(rec.predicted_invoked_skills)
        expected = set(rec.ground_truth_expected_skills)
        forbidden = set(rec.ground_truth_forbidden_skills)

        # Record-level 指标
        if predicted & forbidden:
            over_count += 1
        if expected - predicted:
            under_count += 1
        if predicted == expected:
            perfect_count += 1

        # Per-skill 计数
        for skill in all_skill_names:
            in_expected = skill in expected
            in_forbidden = skill in forbidden
            invoked = skill in predicted

            if in_expected and invoked:
                tp[skill] += 1
            elif in_forbidden and invoked:
                fp[skill] += 1
            elif in_expected and not invoked:
                fn[skill] += 1
            elif in_forbidden and not invoked:
                tn[skill] += 1
            # 既不在 expected 也不在 forbidden → 不关心，不计

    # ── 计算 per-skill 指标 ─────────────────────────────────────────
    per_skill: dict[str, SkillRoutingMetrics] = {}
    precisions = []
    recalls = []
    f1s = []

    for skill in all_skill_names:
        p_denom = tp[skill] + fp[skill]
        r_denom = tp[skill] + fn[skill]
        precision = tp[skill] / p_denom if p_denom > 0 else 0.0
        recall = tp[skill] / r_denom if r_denom > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        per_skill[skill] = SkillRoutingMetrics(
            precision=precision,
            recall=recall,
            f1=f1,
            true_positive=tp[skill],
            false_positive=fp[skill],
            false_negative=fn[skill],
            true_negative=tn[skill],
        )
        if r_denom > 0 or p_denom > 0:
            precisions.append(precision)
            recalls.append(recall)
            f1s.append(f1)

    macro_precision = sum(precisions) / len(precisions) if precisions else 0.0
    macro_recall = sum(recalls) / len(recalls) if recalls else 0.0
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0

    return RoutingMetrics(
        macro_precision=macro_precision,
        macro_recall=macro_recall,
        macro_f1=macro_f1,
        over_invocation_rate=over_count / evaluated_count,
        under_invocation_rate=under_count / evaluated_count,
        perfect_match_rate=perfect_count / evaluated_count,
        evaluated_count=evaluated_count,
        per_skill=per_skill,
    )
