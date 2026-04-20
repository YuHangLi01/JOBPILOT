# 场景 A 评估框架

对 JD 路由 LangGraph 进行端到端量化评估，产出 4 项核心指标 + Baseline 对比报告 + 雷达图。

---

## 目录结构

```
evaluation/
├── datasets/
│   └── loader.py              # 加载 jd_labeled.jsonl → EvaluationExample
├── runners/
│   ├── scenario_a_runner.py   # RunRecord + ScenarioARunner（并发限流 + 断点续跑）
│   └── baseline_runner.py     # 全选 Skill 的 Baseline 图
├── metrics/
│   ├── classification.py      # JD 分类指标（joint accuracy / per-field F1）
│   ├── routing.py             # Skill 路由指标（over/under-invocation + per-skill F1）
│   ├── latency.py             # 延迟分布（P50/P95/P99 + per-node）
│   └── cost.py                # Token 成本对比
└── reports/
    ├── renderer.py            # Markdown 报告生成（6 章节）
    └── plots.py               # 5 张 PNG（含雷达图）
```

---

## 快速开始

### 前置条件

```bash
cd python-agent
uv sync --extra eval   # 安装 scikit-learn / matplotlib / seaborn / tqdm / pandas
```

### Step 1 — 小样本验证（先跑通）

```bash
uv run python scripts/run_scenario_a_eval.py --mode main --sample 50 \
    --output evaluation/runs/main_50.jsonl
```

### Step 2 — 全量主图评估（约 17 分钟）

```bash
# 建议在 tmux 中运行防断联
tmux new-session -s eval_main
uv run python scripts/run_scenario_a_eval.py --mode main --sample 500 \
    --output evaluation/runs/main_$(date +%Y%m%d).jsonl
```

### Step 3 — 全量 Baseline 评估

```bash
uv run python scripts/run_scenario_a_eval.py --mode baseline --sample 500 \
    --output evaluation/runs/baseline_$(date +%Y%m%d).jsonl
```

### Step 4 — 生成对比报告

```bash
uv run python scripts/render_scenario_a_report.py \
    --main evaluation/runs/main_20260501.jsonl \
    --baseline evaluation/runs/baseline_20260501.jsonl \
    --output evaluation/reports/scenario_a_v1.md
```

报告位于 `evaluation/reports/scenario_a_v1.md`，图表位于 `evaluation/reports/figures/`。

---

## 断点续跑

`ScenarioARunner` 自动加载已完成的 `jd_id`，重复执行同一 `--output` 路径时跳过已完成条目：

```bash
# 中断后继续（指定同一输出文件）
uv run python scripts/run_scenario_a_eval.py --mode main --sample 500 \
    --output evaluation/runs/main_20260501.jsonl
```

---

## 评估指标

| 指标 | 目标 | 算法 |
|------|------|------|
| JD 分类 joint accuracy | > 0.90 | 五维全对才算对 |
| JD 分类 Macro F1 (job_type) | > 0.85 | sklearn classification_report |
| Skill 路由 Macro F1 | > 0.85 | 多标签 per-skill F1 宏平均 |
| Over-invocation Rate | < 0.10 | 触发 forbidden skill 的记录比例 |
| 端到端 P95 延迟 | < 8s | numpy.percentile |
| Token 降幅 vs Baseline | ≥ 30% | (baseline - main) / baseline |

---

## Baseline 设计

Baseline = 与主图完全相同的 LangGraph，但 `dispatch_skills` 节点替换为「全选」：

```python
# baseline_runner.py
async def dispatch_all_skills(state):
    register_all_skills()
    return {"invoked_skills": [s.name for s in registry.all()], "skipped_skills": []}
```

目的：量化「有路由 vs 无路由」的效果与 Token 成本差异，保证其他变量（LLM 版本、提示词）完全一致。

---

## 图表说明

| 文件 | 内容 |
|------|------|
| `classification_confusion_matrix_{field}.png` | 各字段混淆矩阵热力图 |
| `routing_f1_per_skill_bar.png` | 各 Skill P/R/F1 水平柱状图 |
| `latency_distribution_histogram.png` | 延迟分布（主图 vs Baseline） |
| `cost_comparison_bar.png` | Token / LLM calls / 费用对比 |
| `five_dim_radar.png` | 五维雷达图（答辩用） |

---

## 运行单测

```bash
uv run pytest tests/evaluation/ -v
# 44 个测试，无网络调用
```
