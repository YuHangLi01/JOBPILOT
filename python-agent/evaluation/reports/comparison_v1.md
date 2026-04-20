# JobPilot Agent vs Baseline · 综合对比报告 v1

**执行时间**:2026-04-19
**主图评估集**:500 条 labeled JD,DeepSeek-chat(temperature=0)
**Baseline**:强制调用所有 6 个 Skill 的版本(同数据集、同模型)
**数据来源**:`evaluation/runs/main_v1.jsonl` + `evaluation/runs/baseline_v1.jsonl`
**本报告** = 对 `scenario_a_v1.md` 的**对比视角**提炼,详细口径请参考原报告。

---

## 1. 摘要

![五维雷达图](figures/five_dim_radar.png)

本项目(主图 + 规则路由)相对于 Baseline(强制全调)的核心差异:

| 维度 | 主图 | Baseline | 差异 |
|---|---|---|---|
| Over-invocation Rate | **0.006** | 1.000 | **-99.4 pp** |
| 总 Token 消耗 | 1,458,123 | 2,026,761 | **-28.1%** |
| 总 LLM Calls | 1,749 | 2,439 | -28.3% |
| P95 延迟 | 76,438ms | 82,558ms | -7.4% |
| P50 延迟 | 61,022ms | 75,703ms | -19.4% |
| 估算费用(¥) | ¥1.46 | ¥2.03 | -28.1% |

## 2. 结论

1. **规则路由策略成立**:Over-invocation 从 100% 压到 0.6%,证明"should_invoke 规则 + 依赖拓扑排序"比"tool-calling 让 LLM 自己选"**更省、更稳、更可预测**。
2. **Token 降幅 28.1%**,距离 30% 目标差 1.9 pp。进一步降本空间在 `final_synthesis` prompt 压缩(W6 P6.1 已落地 ≥50% 压缩,待回归验证)。
3. **延迟 P95 76.4s 明显超 8s 目标**,瓶颈在 `final_synthesis`(占 65%,mean 35s / P95 49s)。W6 P6.1 优化方向:Embedding LRU 缓存 + prompt 裁剪 + httpx 连接池复用。
4. **分类准确率待提升**:Joint Accuracy 0.008 的主因是 `sub_type` 自由文本字段(LLM 生成近义词如 "backend_dev" vs "backend_engineer"),下一版固化候选词表或改用语义相似度比对。

## 3. 分维度对比

### 3.1 分类准确率对比

Baseline 强制全调策略下不做分类评估(它不依赖分类结果),故仅列主图:

| 字段 | Accuracy | Macro F1 |
|---|---|---|
| job_type | 0.648 | 0.648 |
| sub_type | 0.010 | 0.001 |
| level | 0.810 | 0.709 |
| locale | 0.994 | 0.986 |
| channel | 0.934 | 0.768 |

**读法**:locale / channel 表现好(标签封闭集),job_type / level 中等,sub_type 短板(开放文本)。

### 3.2 Skill 路由对比

| 指标 | 主图 | Baseline |
|---|---|---|
| Macro Precision | 0.651 | 低(全调全误) |
| Macro Recall | 0.476 | 1.000(全调全中) |
| Macro F1 | 0.531 | — |
| Over-invocation | **0.006** | **1.000** |
| Under-invocation | 0.650 | 0.000 |
| Perfect Match | 0.232 | 极低 |

**读法**:主图是"宁可漏调,不乱调";Baseline 是"都调了反正不漏",但代价是成本翻倍。
两种极端之间,主图接近"精准模式"但召回偏低(github_scan / portfolio_check 未注入测试字段,should_invoke 规则直接拒绝)。

### 3.3 延迟对比(毫秒)

| 分位数 | 主图 | Baseline | 差异 |
|---|---|---|---|
| P50 | 61,022 | 75,703 | -19.4% |
| P90 | 73,939 | 80,271 | -7.9% |
| P95 | 76,438 | 82,558 | -7.4% |
| P99 | 88,981 | 97,793 | -9.0% |
| Mean | 51,701 | 76,066 | -32.0% |

![延迟分布](figures/latency_distribution_histogram.png)

**读法**:P50 差异大(-19%)、P95 差异小(-7%),说明"路由成功时提速明显,但尾部 case 主图也会卡在 final_synthesis 长 prompt 上"。这是 P6.1 的直接靶点。

### 3.4 成本对比

| 指标 | 主图 | Baseline | 降幅 |
|---|---|---|---|
| 总 Tokens | 1,458,123 | 2,026,761 | 28.1% |
| 平均 Tokens/JD | 2,916 | 4,062 | 28.2% |
| 总 LLM Calls | 1,749 | 2,439 | 28.3% |
| 估算费用 | ¥1.46 | ¥2.03 | 28.1% |

> 定价:¥0.0010/1K tokens(DeepSeek 混合估算)

![成本对比](figures/cost_comparison_bar.png)

## 4. 可回溯

- 原始 JSONL(500 条 × 2):`evaluation/runs/main_v1.jsonl` / `baseline_v1.jsonl`
- 每条记录字段:`jd_id / run_label / predicted_classification / predicted_invoked_skills / total_latency_ms / per_node_latency_ms / total_tokens / llm_calls / success / errors`
- 完整详表(含 bad case、混淆矩阵、per-skill 指标):[`scenario_a_v1.md`](scenario_a_v1.md)
- 对话层评估:[`replay_evaluation_v1.md`](replay_evaluation_v1.md) · [`stage_prediction_v1.md`](stage_prediction_v1.md) · [`checkpoint_consistency_v1.md`](checkpoint_consistency_v1.md)

## 5. 改进路线(W6 收口)

1. **延迟**:P6.1 Embedding LRU 缓存 + final_synthesis prompt 压缩(已落地代码,待真机回归)
2. **成本**:prompt 压缩预计再降 15-20% token(叠加后可破 40%)
3. **分类**:sub_type 固定词表,预计 joint_accuracy 升至 0.6+
4. **路由**:给 github_scan / portfolio_check 评估数据注入测试字段
