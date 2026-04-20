"""场景 A 评估报告生成器。

生成 Markdown 格式的 scenario_a_v1.md，包含：
1. 摘要表格
2. JD 分类指标（per-field F1 + 混淆矩阵引用）
3. Skill 路由指标
4. 延迟指标
5. 成本对比
6. 错误分析（bad cases）

设计说明：
- 使用 Python f-string 模板，无额外依赖
- 图表以相对路径引用（报告与 figures/ 在同一目录下）
- Bad case 分析从 RunRecord 中按错误类型分类，取代表性样本
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from jobpilot_agent.evaluation.metrics.classification import ClassificationMetrics
    from jobpilot_agent.evaluation.metrics.cost import CostComparison
    from jobpilot_agent.evaluation.metrics.latency import LatencyMetrics
    from jobpilot_agent.evaluation.metrics.routing import RoutingMetrics
    from jobpilot_agent.evaluation.runners.scenario_a_runner import RunRecord


def _check(value: float, target: float, higher_better: bool = True) -> str:
    """返回 ✅ 或 ❌ 的 ASCII 替代（跨平台）。"""
    if higher_better:
        return "[OK]" if value >= target else "[FAIL]"
    else:
        return "[OK]" if value <= target else "[FAIL]"


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _ms(v: float) -> str:
    return f"{v:.0f}ms"


def _extract_bad_cases(
    records: "list[RunRecord]",
    max_cases: int = 6,
) -> list[dict[str, Any]]:
    """从 RunRecord 中抽取代表性 bad case。

    分三类：
    1. 分类错误（predicted_classification 与 ground_truth 不一致）
    2. Over-invocation（调用了 forbidden skill）
    3. Under-invocation（漏调了 expected skill）

    每类取 max_cases//3 个。
    """
    per_type = max_cases // 3 or 1
    bad_cases: list[dict[str, Any]] = []

    # 分类错误
    clf_errors = []
    for r in records:
        if not r.success or not r.predicted_classification:
            continue
        mismatches = {
            f: (r.ground_truth_labels.get(f), r.predicted_classification.get(f))
            for f in ["job_type", "level", "locale", "channel"]
            if r.ground_truth_labels.get(f) != r.predicted_classification.get(f)
        }
        if mismatches:
            clf_errors.append((len(mismatches), r, mismatches))
    clf_errors.sort(key=lambda x: -x[0])
    for _, r, mismatches in clf_errors[:per_type]:
        bad_cases.append({
            "type": "分类错误",
            "jd_id": r.jd_id,
            "jd_preview": r.final_result_preview or (r.ground_truth_labels.get("position") or "（无预览）"),
            "detail": f"字段不匹配：{mismatches}",
            "ground_truth": {k: v for k, v in r.ground_truth_labels.items() if k in ["job_type", "level"]},
            "predicted": {k: v for k, v in r.predicted_classification.items() if k in ["job_type", "level"]},
        })

    # Over-invocation
    for r in records:
        if not r.success:
            continue
        forbidden_invoked = set(r.predicted_invoked_skills) & set(r.ground_truth_forbidden_skills)
        if forbidden_invoked:
            bad_cases.append({
                "type": "Over-invocation",
                "jd_id": r.jd_id,
                "jd_preview": r.final_result_preview or "（无预览）",
                "detail": f"不应调用但被触发：{sorted(forbidden_invoked)}",
                "ground_truth": {"forbidden": r.ground_truth_forbidden_skills},
                "predicted": {"invoked": r.predicted_invoked_skills},
            })
        if len([c for c in bad_cases if c["type"] == "Over-invocation"]) >= per_type:
            break

    # Under-invocation
    for r in records:
        if not r.success:
            continue
        missing = set(r.ground_truth_expected_skills) - set(r.predicted_invoked_skills)
        if missing:
            bad_cases.append({
                "type": "Under-invocation",
                "jd_id": r.jd_id,
                "jd_preview": r.final_result_preview or "（无预览）",
                "detail": f"应调用但未触发：{sorted(missing)}",
                "ground_truth": {"expected": r.ground_truth_expected_skills},
                "predicted": {"invoked": r.predicted_invoked_skills},
            })
        if len([c for c in bad_cases if c["type"] == "Under-invocation"]) >= per_type:
            break

    return bad_cases[:max_cases]


def _render_bad_cases_section(cases: list[dict[str, Any]]) -> str:
    if not cases:
        return "_暂无 bad case（所有样本均正确）_\n"

    lines = []
    for i, c in enumerate(cases, 1):
        lines.append(f"### Bad Case {i}：{c['type']}")
        lines.append(f"- **JD ID**: `{c['jd_id']}`")
        lines.append(f"- **问题**: {c['detail']}")
        lines.append(f"- **Ground Truth**: `{c.get('ground_truth')}`")
        lines.append(f"- **Predicted**: `{c.get('predicted')}`")
        if c.get("jd_preview") and c["jd_preview"] != "（无预览）":
            preview = str(c["jd_preview"])[:120] + "..." if len(str(c["jd_preview"])) > 120 else c["jd_preview"]
            lines.append(f"- **输出预览**: {preview}")
        lines.append("")
    return "\n".join(lines)


def generate_report(
    clf_metrics: "ClassificationMetrics",
    routing_metrics: "RoutingMetrics",
    main_latency: "LatencyMetrics",
    baseline_latency: "LatencyMetrics",
    cost: "CostComparison",
    main_records: "list[RunRecord]",
    baseline_records: "list[RunRecord]",
    output_path: str | Path,
    model_name: str = "deepseek-chat",
    figures_rel_path: str = "figures",
) -> str:
    """生成完整评估报告 Markdown 并写入文件。

    Args:
        clf_metrics: 分类指标。
        routing_metrics: 路由指标。
        main_latency: 主图延迟。
        baseline_latency: Baseline 延迟。
        cost: 成本对比。
        main_records: 主图运行记录（用于 bad case 分析）。
        baseline_records: Baseline 运行记录（用于延迟直方图引用）。
        output_path: 报告输出路径。
        model_name: 使用的 LLM 模型名称。
        figures_rel_path: 图片相对路径（相对于报告所在目录）。

    Returns:
        生成的 Markdown 字符串。
    """
    run_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_main = clf_metrics.evaluated_count
    total_base = baseline_latency.evaluated_count

    # ── 摘要指标 ────────────────────────────────────────────────────
    joint_acc = clf_metrics.joint_accuracy
    macro_f1 = routing_metrics.macro_f1
    over_inv = routing_metrics.over_invocation_rate
    p95 = main_latency.p95_ms
    token_red = cost.token_reduction_pct

    job_type_f1 = clf_metrics.per_field.get("job_type")
    job_type_macro_f1 = job_type_f1.macro_f1 if job_type_f1 else 0.0

    # ── 各字段 F1 表 ────────────────────────────────────────────────
    clf_table_rows = []
    for field in ["job_type", "sub_type", "level", "locale", "channel"]:
        fm = clf_metrics.per_field.get(field)
        if fm:
            clf_table_rows.append(
                f"| {field} | {fm.accuracy:.3f} | {fm.macro_f1:.3f} | {fm.weighted_f1:.3f} |"
            )
    clf_table = "\n".join(clf_table_rows)

    # ── Skill F1 表 ─────────────────────────────────────────────────
    routing_rows = []
    for skill, sm in sorted(routing_metrics.per_skill.items()):
        routing_rows.append(
            f"| {skill} | {sm.precision:.3f} | {sm.recall:.3f} | {sm.f1:.3f} "
            f"| {sm.true_positive} | {sm.false_positive} | {sm.false_negative} |"
        )
    routing_table = "\n".join(routing_rows)

    # ── 延迟各节点表 ────────────────────────────────────────────────
    node_rows = []
    for node, nl in sorted(main_latency.per_node.items()):
        node_rows.append(f"| {node} | {nl.mean_ms:.0f}ms | {nl.p95_ms:.0f}ms |")
    node_table = "\n".join(node_rows)

    # ── Bad Cases ───────────────────────────────────────────────────
    bad_cases = _extract_bad_cases(main_records, max_cases=6)
    bad_cases_section = _render_bad_cases_section(bad_cases)

    report = f"""# 场景 A 评估报告

**执行时间**：{run_time}
**评估集**：{total_main} 条 labeled JD（主图）/ {total_base} 条（Baseline）
**模型**：{model_name}（temperature=0）
**定价**：¥{cost.token_price_per_1k_cny:.4f}/1K tokens（混合估算）

---

## 摘要

| 指标 | 主图（本项目） | Baseline（全 Skill） | 目标 | 达成 |
|---|---|---|---|---|
| JD 分类 joint accuracy | {joint_acc:.3f} | — | > 0.90 | {_check(joint_acc, 0.90)} |
| job_type Macro F1 | {job_type_macro_f1:.3f} | — | > 0.85 | {_check(job_type_macro_f1, 0.85)} |
| Skill 路由 Macro F1 | {macro_f1:.3f} | — | > 0.85 | {_check(macro_f1, 0.85)} |
| Over-invocation Rate | {over_inv:.3f} | 1.000 | < 0.10 | {_check(over_inv, 0.10, higher_better=False)} |
| 端到端 P95 延迟 | {_ms(p95)} | {_ms(baseline_latency.p95_ms)} | < 8000ms | {_check(p95, 8000, higher_better=False)} |
| Token 降幅 vs Baseline | {_pct(token_red)} | — | ≥ 30% | {_check(token_red, 0.30)} |

---

## 1. JD 分类

### 1.1 联合准确率

五维全对才算对：**{joint_acc:.3f}**（共 {total_main} 条）

### 1.2 各字段独立指标

| 字段 | Accuracy | Macro F1 | Weighted F1 |
|------|----------|----------|-------------|
{clf_table}

### 1.3 混淆矩阵

各字段混淆矩阵图见：

- ![job_type 混淆矩阵]({figures_rel_path}/classification_confusion_matrix_job_type.png)
- ![level 混淆矩阵]({figures_rel_path}/classification_confusion_matrix_level.png)
- ![locale 混淆矩阵]({figures_rel_path}/classification_confusion_matrix_locale.png)
- ![channel 混淆矩阵]({figures_rel_path}/classification_confusion_matrix_channel.png)

---

## 2. Skill 路由

**Macro Precision**: {routing_metrics.macro_precision:.3f}
**Macro Recall**: {routing_metrics.macro_recall:.3f}
**Macro F1**: {routing_metrics.macro_f1:.3f}

| 指标 | 值 |
|------|----|
| Over-invocation Rate（调了 forbidden） | {over_inv:.3f} ({_check(over_inv, 0.10, higher_better=False)}) |
| Under-invocation Rate（漏调 expected） | {routing_metrics.under_invocation_rate:.3f} |
| Perfect Match Rate（完全匹配） | {routing_metrics.perfect_match_rate:.3f} |

### 2.1 Per-Skill 指标

| Skill | Precision | Recall | F1 | TP | FP | FN |
|-------|-----------|--------|----|----|----|----|
{routing_table}

![Skill 路由 F1 柱状图]({figures_rel_path}/routing_f1_per_skill_bar.png)

---

## 3. 延迟

| 分位数 | 主图 | Baseline |
|--------|------|----------|
| P50 | {_ms(main_latency.p50_ms)} | {_ms(baseline_latency.p50_ms)} |
| P90 | {_ms(main_latency.p90_ms)} | {_ms(baseline_latency.p90_ms)} |
| **P95** | **{_ms(main_latency.p95_ms)}** | **{_ms(baseline_latency.p95_ms)}** |
| P99 | {_ms(main_latency.p99_ms)} | {_ms(baseline_latency.p99_ms)} |
| Mean | {_ms(main_latency.mean_ms)} | {_ms(baseline_latency.mean_ms)} |

### 3.1 各节点耗时（主图 P95）

| 节点 | Mean | P95 |
|------|------|-----|
{node_table}

![延迟分布]({figures_rel_path}/latency_distribution_histogram.png)

---

## 4. 成本

| 指标 | 主图 | Baseline | 降幅 |
|------|------|----------|------|
| 总 Tokens | {cost.main.total_tokens:,} | {cost.baseline.total_tokens:,} | {_pct(token_red)} |
| 平均 Tokens/JD | {cost.main.avg_tokens_per_jd:.0f} | {cost.baseline.avg_tokens_per_jd:.0f} | — |
| 总 LLM Calls | {cost.main.total_llm_calls:,} | {cost.baseline.total_llm_calls:,} | {_pct(cost.llm_call_reduction_pct)} |
| 估算费用（CNY） | ¥{cost.main.estimated_cost_cny:.2f} | ¥{cost.baseline.estimated_cost_cny:.2f} | {_pct(cost.cost_saved_pct)} |

> 定价：¥{cost.token_price_per_1k_cny:.4f}/1K tokens（deepseek-chat 混合估算）

![成本对比]({figures_rel_path}/cost_comparison_bar.png)

---

## 5. 综合雷达图

五维评估（均为越大越好）：分类准确率 · 路由 F1 · 低 Over-invocation · 低延迟 P95 · 低成本

![五维雷达图]({figures_rel_path}/five_dim_radar.png)

---

## 6. 错误分析

{bad_cases_section}

### 改进建议

1. **分类字段 sub_type 准确率偏低**（标注标准不一致）
   - 原因：sub_type 是自由文本字段，LLM 倾向于生成近义词（如 "backend_dev" vs "backend_engineer"）
   - 改进：在 classify_jd 提示词中固定 sub_type 候选词表，或在评估时使用语义相似度匹配

2. **under-invocation 漏调部分 Skill**
   - 原因：`should_invoke` 规则较保守（如 `github_scan` 需要 senior/lead 且有 github_username）
   - 改进：评估时注入 github_username，或调整 level 阈值

3. **延迟 P95 受外部 API 影响**
   - 原因：interview_rag 的 Milvus 检索和 github_scan 的 GitHub API 调用增加尾部延迟
   - 改进：为外部 API 调用增加更积极的超时设置（如 5s），降低 P99

---

*报告由 `render_scenario_a_report.py` 自动生成，基于 {total_main} 条全量评估数据。*
"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    return report
