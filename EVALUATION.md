# JobPilot Agent · 评估方法论

本项目坚持"每一个功能 → 对应一个可量化指标 → 对应一份可复现报告"。所有指标均有 JSONL 原始数据可回溯到 `python-agent/evaluation/runs/`。

---

## 1. 三层评估金字塔

```text
         ┌─────────────────────────┐
         │  Scenario B / 对话质量   │   (面试子图)
         │  Replay / Stage / Ckpt  │
         └──────────┬──────────────┘
                    │
         ┌──────────▼──────────────┐
         │  Scenario A / 编排质量   │   (主图 + Skill 路由)
         │  Accuracy · F1 · Cost   │
         └──────────┬──────────────┘
                    │
         ┌──────────▼──────────────┐
         │  RAGAS / 检索质量        │   (RAG 层基础)
         │  4 件套 + 分布统计       │
         └──────────────────────────┘
```

每一层独立评估,报告独立。层层递进:底层不好,上层就无从谈起。

---

## 2. 第一层:检索质量(RAGAS)

### 2.1 四件套指标

| 指标 | 目标 | 说明 |
|---|---|---|
| Context Relevance | > 0.75 | 检索到的 context 与 query 相关度 |
| Context Recall | > 0.80 | ground truth answer 中的事实是否被 context 覆盖 |
| Faithfulness | > 0.85 | 生成答案中事实是否都有 context 依据(幻觉检测) |
| Answer Relevancy | > 0.80 | 生成答案与 query 相关度 |

### 2.2 实现细节

- **数据源**:从 500 条 JD 路由数据集派生 100 条 RAGAS 评估集。30 条人工标注 ground_truth,70 条 LLM 辅助生成。
- **LLM backend**:ragas 默认用 OpenAI,本项目替换为 **DeepSeek**(降本 + 国内稳定)+ HuggingFace 嵌入。见 `evaluation/ragas/ragas_runner.py`。
- **Metrics wrapper**:`safe_float()` 处理 RAGAS 内部 NaN(一些 edge case 会出 NaN)。
- **聚合**:`aggregate_results()` 支持按公司/职位分组,便于定位短板。

### 2.3 复现

```bash
cd python-agent
uv run python scripts/run_ragas_eval.py build      # 从 500 条 JD 抽 100 条
uv run python scripts/run_ragas_eval.py collect    # 跑主图收集 response + contexts
uv run python scripts/run_ragas_eval.py evaluate   # 跑 RAGAS
uv run python scripts/run_ragas_eval.py render     # 生成 6 章 Markdown 报告
```

### 2.4 状态

RAGAS 四件套 runner 已落地(见 `evaluation/ragas/` 代码与 `tests/ragas/` 23 条单元测试),等待真机跑一轮后出 `ragas_v1.md` 报告。未出报告前,不宣称具体分数。

---

## 3. 第二层:编排质量(Scenario A)

### 3.1 指标体系

| 维度 | 指标 | 目标 | 来源 |
|---|---|---|---|
| 分类 | Joint Accuracy(5 维全对) | > 0.90 | `ClassificationMetrics` |
| 分类 | job_type Macro F1 | > 0.85 | 同上 |
| 路由 | Skill Routing Macro F1 | > 0.85 | `RoutingMetrics` |
| 路由 | Over-invocation Rate | < 0.10 | 同上 |
| 延迟 | 端到端 P95 | < 8000ms | `LatencyMetrics` |
| 成本 | Token 降幅 vs Baseline | ≥ 30% | `CostComparison` |

### 3.2 实测结果(v1,500 条全量)

来自 [`python-agent/evaluation/reports/scenario_a_v1.md`](python-agent/evaluation/reports/scenario_a_v1.md):

| 指标 | 主图 | Baseline | 目标 | 状态 |
|---|---|---|---|---|
| Joint accuracy | 0.008 | — | > 0.90 | ❌(sub_type 标注一致性是主因) |
| job_type Macro F1 | 0.648 | — | > 0.85 | ❌ |
| Skill Routing Macro F1 | 0.531 | — | > 0.85 | ❌ |
| **Over-invocation Rate** | **0.006** | **1.000** | < 0.10 | ✅ |
| P95 latency | 76438ms | 82558ms | < 8000ms | ❌(W6 P6.1 优化中) |
| Token 降幅 | **28.1%** | — | ≥ 30% | ⚠️ 接近达标(-1.9 pp) |

### 3.3 Baseline 定义

> **Baseline = 强制调用所有 6 个 Skill 的版本**

这样对比是**公平的"有路由 vs 无路由"**,而非"LLM vs 其他 LLM"。Over-invocation 从 Baseline 的 100% 降到主图的 0.6% 是这个设计最直接的收益。

### 3.4 Per-Skill 路由 F1(v1)

| Skill | Precision | Recall | F1 |
|---|---|---|---|
| en_translate | 0.968 | 0.984 | **0.976** |
| tech_stack_extract | 1.000 | 0.876 | **0.934** |
| interview_rag | 1.000 | 0.700 | **0.824** |
| gpa_check | 0.941 | 0.296 | 0.451 |
| github_scan | 0.000 | 0.000 | 0.000 |
| portfolio_check | 0.000 | 0.000 | 0.000 |

> github_scan / portfolio_check 本轮 F1 为 0 的主因:500 条评估集里没有注入 `github_username` / `portfolio_url` 字段,should_invoke 规则拒绝触发。属于评估集设计问题,不是代码逻辑问题,下一版会注入测试用字段。

### 3.5 Per-Node 延迟分解(v1 主图)

| 节点 | Mean | P95 | 占比 |
|---|---|---|---|
| parse_jd | 7755ms | 11963ms | 15% |
| classify_jd | 2391ms | 3155ms | 4% |
| invoke_skills_parallel | 7194ms | 15016ms | 20% |
| **final_synthesis** | **35124ms** | **49483ms** | **65%** |

> final_synthesis 是延迟瓶颈。W6 P6.1 已做 prompt 压缩(≥50%)+ Embedding LRU 缓存,待真机验证收益。

### 3.6 复现

```bash
cd python-agent

# 跑主图全量评估(~20 min)
uv run python scripts/run_scenario_a.py \
  --mode main --dataset knowledge-base/data/labeled/jd_labeled.jsonl \
  --out evaluation/runs/main_v1.jsonl

# 跑 Baseline(~20 min)
uv run python scripts/run_scenario_a.py \
  --mode baseline --dataset knowledge-base/data/labeled/jd_labeled.jsonl \
  --out evaluation/runs/baseline_v1.jsonl

# 生成报告
uv run python scripts/render_scenario_a_report.py \
  --main evaluation/runs/main_v1.jsonl \
  --baseline evaluation/runs/baseline_v1.jsonl \
  --out evaluation/reports/scenario_a_v1.md
```

---

## 4. 第三层:对话质量(Scenario B)

面试子图三项独立评估。

### 4.1 Interview Replay(创新点)

把主观的"面试逼真度"转换为客观的"下一问预测":

```
给 Bot:  前 N 个 turn + stage context
让 Bot:  生成 K 个候选下一问
对比:    与真实面经的下一问做语义相似度(bge-m3)+ Rank@K
```

指标与实测(30 对 pair,[`replay_evaluation_v1.md`](python-agent/evaluation/reports/replay_evaluation_v1.md)):

| 指标 | 目标 | 实测 | 状态 |
|---|---|---|---|
| Semantic Similarity 均值 | > 0.70 | **0.480** | ❌ |
| Rank@3 | > 0.60 | **0.933** | ✅ |
| Rank@5 | > 0.85 | **0.933** | ✅ |

> 解读:Bot 出题与真实追问的"语义相同"(SemSim)偏低,但"排进 top-3"(Rank@3)很高 —— 说明 Bot 能覆盖考点方向,但用词和角度有差异。分 stage 看,`project_deep_dive` stage 的 SemSim 均值 0.618 明显高于 `tech_qa` 的 0.435,符合预期(tech_qa 题目颗粒度更细)。

### 4.2 阶段推进准确率

300 条面经样本,让 Bot 根据 history 预测当前 stage:

| 指标 | 目标 | 实测 | 状态 |
|---|---|---|---|
| Accuracy | > 0.85 | **0.723** | ❌ |

详见 [`stage_prediction_v1.md`](python-agent/evaluation/reports/stage_prediction_v1.md)。主要失误:`project_deep_dive → intro` 混淆率 86.4%(两阶段对话特征接近)、`scenario → tech_qa` 混淆率 80%。下一版改进:predict_stage prompt 补 1-2 个 few-shot 示例。

### 4.3 断点续聊一致性(必须 100%)

SIGKILL 强杀 + 重启 + 状态对比,4 个场景 × 2 个 backend(SQLite / Postgres):

| 场景 | SQLite | Postgres |
|---|---|---|
| 5 轮后 kill | ✅(450s) | ⏭️ 需 POSTGRES_TEST_URL |
| 多次 kill | ✅(~400s) | ⏭️ |
| interrupt 期间 kill | ✅(107s) | ⏭️ |
| 并发多 thread | ✅(~400s) | ⏭️ |

6 个一致性字段(current_stage / transcript / performance_signals / stage_round_count / stage_history / candidate_profile)**全部 100% 恢复**。

详见 [`checkpoint_consistency_v1.md`](python-agent/evaluation/reports/checkpoint_consistency_v1.md)。

### 4.4 复现

```bash
cd python-agent

# Replay
uv run python scripts/run_interview_replay.py \
  --dataset knowledge-base/data/clean/interview_structured_filtered.jsonl \
  --n 30 --out evaluation/runs/replay_v1.jsonl

# Stage prediction
uv run python scripts/run_stage_eval.py \
  --dataset knowledge-base/data/clean/interview_structured_filtered.jsonl \
  --n 300 --out evaluation/runs/stage_v1.jsonl

# Checkpoint consistency(SQLite)
UV_PROJECT_ENVIRONMENT=/tmp/jobpilot-venv \
  uv run pytest tests/checkpoint/test_sqlite_kill_restart.py -v -m checkpoint
```

---

## 5. 综合评估:五维雷达

`evaluation/reports/figures/five_dim_radar.png` 将五个关键维度归一化到 [0, 1] 后作雷达图(主图 vs Baseline):

1. 分类准确率(joint_accuracy)
2. Skill 路由 F1(macro)
3. 低 Over-invocation(`1 - over_invocation_rate`)
4. 低延迟(`1 - main.p95 / baseline.p95`,cap 0)
5. 低成本(`1 - main_tokens / baseline_tokens`,cap 0)

实现见 `evaluation/reports/plots.py::plot_five_dim_radar_comparison()`。

---

## 6. 诚实总结

- **确定达标的**:Over-invocation 0.6% ✅、Rank@3 / Rank@5 0.933 ✅、Checkpoint 100% ✅
- **接近达标的**:Token 降幅 28.1%(差 1.9 pp,≥30% 目标)
- **未达标的**:Joint Accuracy 0.008(sub_type 词表未固化)、Stage Accuracy 0.723、Replay SemSim 0.48、P95 76s
- **状态**:W6 正在对 `final_synthesis` 节点延迟与 prompt 规模做 P6.1 专项优化;RAGAS 四件套待真机跑完出报告

**为什么诚实列出失败**:评估体系的价值不在"数字漂亮",而在"能诊断问题"。每一个 ❌ 都已经在对应的报告里写清楚改进方向,可作为下一版 scope 的输入。

---

## 7. 全套一键评估

```bash
cd python-agent
make eval-all-report    # (待补齐 Makefile target;当前分步执行)
```
