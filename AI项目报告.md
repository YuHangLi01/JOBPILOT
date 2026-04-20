# JobPilot Agent · AI 项目报告

> 基于 LangGraph 的求职全流程智能体系统 —— 6 周完整交付的设计、实施与评估报告。

| 项目名称 | JobPilot Agent |
|---|---|
| 赛道定位 | 飞书校园挑战赛 · 开放创新赛道(兼顾 OpenClaw 课题一/二) |
| 起止时间 | 2026-03-15 → 2026-04-19(6 周) |
| 交付形态 | 飞书 IM 内运行的 AI Agent + 双栈开源工程 + 三层评估报告 |
| 仓库 | `jobpilot-feishu`(Node.js Gateway + Python Agent 双栈) |

---

## 目录

1. [摘要](#1-摘要)
2. [项目背景与动机](#2-项目背景与动机)
3. [问题定义](#3-问题定义)
4. [项目目标与范围](#4-项目目标与范围)
5. [技术方案总览](#5-技术方案总览)
6. [六周实施路径](#6-六周实施路径)
7. [评估结果](#7-评估结果)
8. [关键技术决策(ADR 精选)](#8-关键技术决策adr-精选)
9. [工程化实践](#9-工程化实践)
10. [总结与展望](#10-总结与展望)
11. [附录](#11-附录)

---

## 1. 摘要

**JobPilot Agent** 是运行在飞书 IM 中、以 JD 为入口、以复盘报告为出口的端到端求职智能体。系统通过 **RAG 混合检索**、**LangGraph 双图编排**、**6 个模块化 Skill** 和 **三层评估金字塔** 解决传统 LLM 求职工具"无记忆、无结构、无依据"的三大缺陷。

**核心贡献**:

1. **四件套完整落地**:RAG(BM25 + Milvus + RRF + BGE rerank)+ LangGraph(分支/循环/中断/持久化)+ 6 Skill 模块化 + 自建评估框架。
2. **两份自建数据集**:500 条 JD 路由标注 + 643 条结构化面经,合规声明可追溯。
3. **三层评估金字塔**:RAGAS(检索)+ Scenario A(编排,500 条全量)+ Scenario B(对话层:Replay / Stage / Checkpoint)。
4. **创新评估方法 Interview Replay**:把主观的面试逼真度转成客观的"下一问 Rank@K 预测",Rank@3 达 93.3%。
5. **工程化严肃**:OpenAPI 契约 CI 强制同步 + ack-first webhook + SIGKILL 断点续聊一致性 100%。

**关键实测指标**(500 条 JD 全量 + 30 对面经 Replay + 300 条 stage + 4 个 checkpoint 场景):

| 已达标 | 实测 |
|---|---|
| Skill 路由 Over-invocation Rate | **0.6%**(Baseline 100%,降 99.4 pp)|
| Interview Replay Rank@3 | **93.3%**(目标 > 60%)|
| Interview Replay Rank@5 | **93.3%**(目标 > 85%)|
| 断点续聊一致性(4 场景 × 6 字段)| **100%** |
| Token 降幅 vs Baseline | **28.1%**(接近 30% 目标) |

| 攻坚中 | 实测 | 原因 |
|---|---|---|
| P95 端到端延迟 | 76s(目标 8s)| final_synthesis 节点占 65%,W6 P6.1 优化已落地代码待回归 |
| JD 分类 joint_accuracy | 0.008 | sub_type 自由文本字段 LLM 生成近义词,下一版固化词表 |
| Stage 预测 Accuracy | 72.3% | project_deep_dive 与 intro 特征接近,需 few-shot 示例 |

---

## 2. 项目背景与动机

### 2.1 用户场景

求职是学生和早期职场人最高频的"重决策 + 长链路"场景之一。一次完整的求职旅程包括:

```
看到 JD → 评估匹配度 → 定制简历 → 投递 → 准备面试 → 完成面试 → 复盘
```

这 7 步里,每一步都需要大量上下文信息(岗位要求、自身技能、公司面经、历史投递记录),而且**前后步骤相互依赖**。

### 2.2 现有工具的不足

我们系统调研了市面上的 LLM 求职工具(AI 简历 / AI 面试陪练 / AI JD 分析),发现三个共性问题:

| 类型 | 典型产品形态 | 共性问题 |
|---|---|---|
| AI 简历优化 | 单轮对话式 prompt | 每次粘贴 JD 和简历都要重新输入,无法累积 |
| AI 面试陪练 | ChatGPT 装 prompt 模拟面试官 | 多轮后面试官跳戏、问题重复、不分阶段 |
| AI JD 分析 | 直接调 LLM 生成建议 | LLM 编造"大厂面试常考 React Fiber"之类无依据内容 |

本质上,这三类工具都是**把 LLM 当 function call 用**,而 Agent 应有的三个核心能力(状态、结构、事实依据)都没补齐。

### 2.3 飞书作为载体的价值

- **现成的 IM 入口**:用户不用下载新 App,直接在工作生活已用的 IM 里使用
- **现成的副作用落地**:多维表格 = 投递追踪;云文档 = 面试准备材料;Task = 跟进提醒
- **企业场景天然过渡**:从学生求职自然过渡到企业内部的 HR 辅助/员工内推等场景(对齐 OpenClaw 课题)

---

## 3. 问题定义

本项目要解决的核心问题可以浓缩为一句话:

> **如何把 LLM 求职工具从"一次性问答"升级为"有记忆、有结构、有依据"的陪跑系统。**

拆成三个子问题:

### 3.1 子问题 1:无记忆

用户跨会话、跨工具使用时,上下文丢失。每次都要把 JD、简历、偏好重新输入。

**解法**:LangGraph Checkpointer 做对话层持久化 + Redis SessionContext 做跨图桥接 + 个人知识库(user_kb)做长期记忆。

### 3.2 子问题 2:无结构

多轮对话没有状态机,面试 Bot 三轮后跳戏、重复提问、阶段混乱。

**解法**:LangGraph 状态机 —— 面试子图有明确的 5 个阶段(intro / project_deep_dive / tech_qa / scenario / reverse / closing),每阶段可循环追问 2-5 轮,支持 interrupt 等待用户作答。

### 3.3 子问题 3:无依据

LLM 凭空生成"某公司面试常考某知识点",幻觉率高,用户无法验证。

**解法**:RAG 混合检索 —— BM25 精确匹配 + Milvus 向量语义 + RRF 融合。所有"推荐题目 / 公司亮点"都附带 `doc_id` 可追溯到具体面经片段。

---

## 4. 项目目标与范围

### 4.1 范围内(6 周交付)

- ✅ 飞书 IM 入口的完整闭环:粘贴 JD → 分析卡片 → 面试邀请 → 多轮面试 → 复盘报告
- ✅ 6 个 Skill 模块化(tech_stack_extract / gpa_check / en_translate / interview_rag / portfolio_check / github_scan)
- ✅ 主图(JD 路由)+ 面试子图(5 阶段)双图架构
- ✅ 自建 JD 数据集(500 条)+ 面经数据集(643 条)+ RAG 评估集(100 条)
- ✅ 三层评估框架(RAGAS / Scenario A / Scenario B 三件套)
- ✅ Docker Compose 一键起全栈

### 4.2 范围外(明确不做)

- ❌ 模型训练(全部基于已有 LLM:DeepSeek / BGE-M3 / Cross-encoder)
- ❌ 移动端原生 App(依托飞书客户端)
- ❌ 企业 HR 视角反转(留到 V2 对齐 OpenClaw 课题)
- ❌ 真实简历数据入库(合规风险,只用人工撰写 demo 样本)
- ❌ 生产级多租户(单租户单 bot 起步)

### 4.3 成功标准

| 层级 | 指标 | 目标 |
|---|---|---|
| 能力层 | 完成飞书端到端 demo | 一次粘贴 JD 到面试结束全程打通 |
| 编排层 | Skill 路由 Over-invocation | < 10% |
| 编排层 | Token 成本降幅 vs Baseline | ≥ 30% |
| 对话层 | Interview Replay Rank@3 | > 60% |
| 对话层 | 断点续聊一致性 | 100% |
| 检索层 | RAGAS 四件套全部 | > 目标线(0.75-0.85) |
| 工程层 | OpenAPI 契约自动同步 | CI 强制 |

---

## 5. 技术方案总览

### 5.1 双栈架构

```
┌────────────────────────────────────────────────────────────────────┐
│                        飞书开放平台                                  │
│            (IM / 多维表格 / 云文档 / Task)                           │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ Webhook / OpenAPI
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│   Node.js Gateway (Express + TypeScript, port 3000)                │
│   - Webhook 接入(ack-first,3s 内必 200)                          │
│   - 事件去重(in-memory TTL cache)                                 │
│   - 飞书副作用(bitable/doc/task/message)                          │
│   - Orchestrator 路由(Python / legacy fallback)                  │
│   - Intent detection + ChatState(面试中继/JD 路由分流)            │
│   - /internal/feishu/* 反向回调(供 Python 读飞书资源)             │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ HTTP (X-Request-ID)
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│   Python Agent (FastAPI + LangGraph, port 8001)                    │
│   - /jd-routing:JD 路由主图                                        │
│   - /interview/*:面试子图(interrupt/resume)                      │
│   - LangGraph Checkpointer(SQLite / Postgres)                     │
│   - 6 Skill 模块化 + 依赖拓扑排序                                  │
│   - Hybrid RAG(BM25 + Milvus + RRF + BGE rerank)                 │
└──────────────────────────────┬─────────────────────────────────────┘
                               ▼
          ┌──────────────┬──────────────┬──────────────┐
          │   Milvus     │   Postgres   │   Redis      │
          │ jd_kb /      │ checkpoints  │ session_     │
          │ interview_kb │              │ context      │
          │ user_kb      │              │              │
          └──────────────┴──────────────┴──────────────┘
```

#### 5.1.1 为什么双栈?

| 方案 | 优点 | 致命缺点 |
|---|---|---|
| 纯 Node.js | 飞书 SDK 一等公民 | LangChain TS / LangGraph TS 成熟度滞后 Python 约半年;RAGAS 无 TS 版 |
| 纯 Python | AI 生态完整 | 飞书 SDK 覆盖不全;Webhook 稳定性差 |
| **双栈(本项目)** | 各用所长 | 多一次 HTTP 跳转(本地 localhost,~2-5ms) |

#### 5.1.2 黄金法则

> **Node.js 只做"协议翻译"和"副作用",Python 做所有"智能决策"**

这条规则把架构边界划死。Python 想写飞书?必须通过 `POST /internal/feishu/*`(Node.js 暴露、`X-Internal-Secret` 守门)。Python 不持有飞书 token,不直接调飞书 OpenAPI。

#### 5.1.3 契约驱动类型同步

```
python-agent/src/jobpilot_agent/api/schemas.py (Pydantic v2)
          │ uv run python scripts/export_openapi.py
          ▼
contracts/openapi.json
          │ npm run gen:types
          ▼
src/integrations/python-agent/generated.ts
          │ re-exported by
          ▼
src/integrations/python-agent/types.ts
```

`.github/workflows/contract-check.yml` 在 CI 中同时跑这两步。Python 改 schema 但没跑 `make contracts`,PR 直接挂。

---

### 5.2 RAG 混合检索

三库独立部署,走统一 Retriever 接口:

| Collection | 规模 | 动态字段 | 典型过滤 |
|---|---|---|---|
| `jd_kb` | ≥1500 chunk(500 JD × avg 3 段) | `job_type/sub_type/level/locale/channel` | `job_type=tech` |
| `interview_kb` | ≥3000 turn(643 面经 × avg 10 turn) | `role/stage/level/company/year` | `stage=tech_qa` |
| `user_kb` | ≥20 section(4 简历) | `user_id/section` | `user_id=u_default` |

**检索流程**:

1. **BM25Okapi**(jieba 分词 + `TECH_TERMS` 自定义词典)做关键词召回
2. **Milvus HNSW**(BGE-M3 or DeepSeek embedding,dim=1024;M=16, efConstruction=200, ef=64)做向量召回
3. **自实现 RRFRanker**(`k=60` 默认)融合两路
4. **可选 BGE cross-encoder** 重排 top-K

**降级策略**:`RETRIEVAL_FALLBACK_TO_CHROMA=true` 时,Milvus 不可达自动切换本地 Chroma,便于开发调试。

**Embedding 缓存(W6 P6.1)**:`CachedEmbedder` 用 `OrderedDict` + `threading.Lock` 实现零依赖 LRU(默认 10000 条),SHA256 截取 16 字符做 key。`DoubaoEmbedder`(适配 DeepSeek)复用 `httpx.AsyncClient` 连接池。

---

### 5.3 LangGraph 双图编排

#### 5.3.1 主图(JD 路由)

6 节点顺序执行:

```
  parse_jd → classify_jd → dispatch_skills ──┬── invoke_skills_parallel ──┐
                                             │  (asyncio.gather)          │
                                             └── (skip 无 skill)          │
                                                                          ▼
                                                    merge_outputs → final_synthesis
                                                                          │
                                                                          ▼
                                              interview_invitation rule
```

- `dispatch_skills` 是 **Conditional Edges**:根据 `should_invoke(ctx)` 决定下一步走 `invoke` 还是 `skip`
- `invoke_skills_parallel` 是 **并发节点**:`asyncio.gather` 真并发
- `final_synthesis` 后追加 **规则判断** `_should_invite_interview()`,命中则塞 `InterviewInvitation` + 写 Redis

#### 5.3.2 面试子图

5 阶段 + 2 个收尾节点,每阶段可自环 2-5 轮:

```
  init → intro ──┐
                 ├─→ project_deep_dive ──(loop 2-5 轮)
                 │         ↓
                 ├─→ tech_qa ─────────────(loop 2-5 轮)
                 │         ↓
                 ├─→ scenario ────────────(loop 2-5 轮)
                 │         ↓
                 ├─→ reverse ─────────────(候选人反问)
                 │         ↓
                 └─→ closing → evaluate → END
                                ↓
                        InterviewReport(雷达图 + 建议)
```

每个阶段节点用 **interrupt** 挂起,等待 `graph.ainvoke(Command(resume=user_input))` 恢复。

Checkpointer 在每个节点完成时写 state 快照。SIGKILL 打掉进程后,再次 `ainvoke` 会从 checkpoint 恢复,**6 个一致性字段全绿**(见 §7.4)。

#### 5.3.3 两图不嵌套(ADR-003)

主图一次性执行,子图多轮交互,二者运行时形态不同。选择**不嵌套**,改用 Redis SessionContext 桥接:

- 主图跑完 → API 层把 `{classification, parsed_jd, jd_summary}` 写 Redis(key=`session_context:{feishu_chat_id}`, TTL=24h)
- 用户点"开始面试" → `/interview/start` 从 Redis 读 → 补齐 company/position → 启动子图

完整时序图见 [docs/e2e_flow.md](docs/e2e_flow.md)。

---

### 5.4 Skill 模块化与双接口

6 个 Skill:

| Skill | 类型 | 何时触发 |
|---|---|---|
| `tech_stack_extract` | LLM Skill | `job_type=tech`,提取技术栈标签 |
| `gpa_check` | LLM Skill(+正则) | `channel=campus`,检验 GPA 门槛 |
| `en_translate` | LLM Skill | `locale=en`,英文 JD 翻译 |
| `interview_rag` | RAG Skill | 有 company/position,检索面经 |
| `portfolio_check` | 外部 Skill(Node callback) | `job_type=design`,验证作品集链接 |
| `github_scan` | 外部 Skill(GitHub API) | `level in [senior, lead]` 且有 github_username |

**双接口设计**:

```python
class Skill(ABC):
    @abstractmethod
    def should_invoke(self, ctx: JDContext) -> bool: ...

    @abstractmethod
    async def invoke(self, ctx: JDContext) -> SkillOutput: ...

    def to_langchain_tool(self) -> BaseTool:
        """同时导出为 LangChain Tool,支持 tool-calling 备选路径"""
```

- `should_invoke`:业务层规则路由,纯条件判断、轻量、可预测
- `to_langchain_tool`:保留 LLM tool-calling 的备选路径

**实证**:Scenario A 评估显示规则路由 Over-invocation 0.6%,而强制全调 Baseline 是 100%(见 §7.2)。

---

### 5.5 评估框架:三层金字塔

```
         ┌─────────────────────────┐
         │  Scenario B / 对话质量   │  (面试子图)
         │  Replay / Stage / Ckpt  │
         └──────────┬──────────────┘
                    │
         ┌──────────▼──────────────┐
         │  Scenario A / 编排质量   │  (主图 + Skill 路由)
         │  Accuracy · F1 · Cost   │
         └──────────┬──────────────┘
                    │
         ┌──────────▼──────────────┐
         │  RAGAS / 检索质量        │  (RAG 层基础)
         │  4 件套 + 分布统计       │
         └──────────────────────────┘
```

每一层独立评估、报告独立。层层递进:底层不好,上层无从谈起。

- **RAGAS 四件套**:Context Relevance / Context Recall / Faithfulness / Answer Relevancy(见 [EVALUATION.md §2](EVALUATION.md))
- **Scenario A**:Joint Accuracy / Macro F1 / Over-invocation / P95 Latency / Token Cost(500 条全量)
- **Scenario B**:Interview Replay(下一问 Rank@K)/ Stage Prediction / Checkpoint Consistency

详细指标口径、复现命令见 [EVALUATION.md](EVALUATION.md)。

---

## 6. 六周实施路径

### Week 1 · 双栈脚手架 + JD 数据集(2026-03-15 至 2026-03-21)

**目标**:搭好双栈通信骨架,完成 500 条 JD 标注数据集。

- **P1.1 双栈脚手架**
  - Python FastAPI + LangGraph stub + Pydantic v2 schema
  - Node.js Gateway 接入 Feishu webhook,ack-first 异步处理
  - OpenAPI 契约 + TS 类型自动生成
  - `/internal/feishu/docs/read` 反向回调 stub
- **P1.2 500 条 JD 数据集**
  - HF `jobs.csv` + 多平台公开 JD 清洗
  - 去重 + PII 剔除 + 正则抽取 company/position
- **P1.3 JD 路由 5 维标注**
  - DeepSeek-chat 做 LLM 初标
  - 30 条高分歧样本人工复核(改动率 12.4%)

**关键产出**:`knowledge-base/data/labeled/jd_labeled.jsonl`(500 条)、`contracts/openapi.json`(首版)。

### Week 2 · RAG 检索层 + 面经数据集(2026-03-22 至 2026-03-28)

**目标**:混合检索完整跑通,面经数据集灌入向量库。

- **P2.1 643 条结构化面经**
  - 多源面经清洗 + 结构化抽取(turn_id / role / stage / content)
  - `quality_score` 过滤(≥0.6 保留)
- **P2.2 Hybrid RAG 检索层**
  - BM25Okapi(jieba + TECH_TERMS)
  - Milvus HNSW(BGE-M3 dim=1024)
  - 自实现 RRFRanker(k=60)
  - 可选 BGE cross-encoder 重排
- **P2.3 三 Collection 灌入**
  - `jd_kb` / `interview_kb` / `user_kb` 独立 schema + 动态字段
  - `kb-ingest` CLI 支持 rebuild-all / incremental

**关键产出**:`python-agent/src/jobpilot_agent/retrieval/*`、`knowledge-base/data/clean/interview_structured_filtered.jsonl`(643 条)。

### Week 3 · 6 Skill + 主图 + Scenario A 评估(2026-03-29 至 2026-04-04)

**目标**:Skill 编排主图跑通,Scenario A 首版评估报告出炉。

- **P3.1 Skill 基础设施**
  - `SkillBase` 抽象类(双接口)
  - `SkillRegistry` 单例 + 依赖拓扑排序
  - `SkillDispatcher` 规则路由
  - `LLMSkillBase` 封装重试、结构化输出
- **P3.2 6 个 Skill 实现**
  - 3 个 LLM Skill + 3 个外部 Skill
- **P3.3 LangGraph 主图**
  - 6 节点 + Conditional Edges + 并发 invoke
  - `POST /api/v1/agent/jd-routing` 真实调用入口
- **P3.4 Scenario A 评估**
  - 500 条 JD 全量跑主图(`main_v1.jsonl`)
  - 500 条 JD 全量跑 Baseline(`baseline_v1.jsonl`)
  - 9 张指标图 + 6 章 Markdown 报告(`scenario_a_v1.md`)

**关键产出**:Skill 生态完整、主图真实调用、Scenario A 首版报告(含五维雷达)。

### Week 4 · 面试子图 + Replay/Stage 评估(2026-04-05 至 2026-04-11)

**目标**:面试子图 5 阶段跑通,Scenario B 三件套评估落地。

- **P4.1 面试子图**
  - 5 阶段节点 + interrupt/resume + Cyclic Graph 自环
  - AsyncSqliteSaver + AsyncPostgresSaver 双 backend
  - `/interview/start` + `/interview/resume` + `/status` API
- **P4.2 Interview Replay**
  - 从面经抽 30 对 pair(history → real_next)
  - Bot 生成 top-5 候选 → bge-m3 语义相似度 + Rank@K
- **P4.3 Stage Prediction**
  - 300 条 stage 样本,Bot 根据 history 预测 stage
  - 混淆矩阵 + per-stage F1
- **P4.4 Checkpoint 断点续聊**
  - 4 个 SIGKILL 场景 × 6 个一致性字段自动化测试

**关键产出**:面试子图、3 份 Scenario B 报告(`replay_evaluation_v1.md` / `stage_prediction_v1.md` / `checkpoint_consistency_v1.md`)。

### Week 5 · 主图↔面试子图集成 + RAGAS + 飞书端到端(2026-04-12 至 2026-04-18)

**目标**:端到端闭环打通,RAGAS 四件套落地。

- **P5.1 主图挂载面试子图**
  - `InterviewInvitation` schema + `_should_invite_interview()` 规则
  - Redis SessionContext(TTL 24h)桥接
  - `/interview/start` 自动从 Redis 读 context 补齐参数
- **P5.2 RAGAS 四件套**
  - 100 条 RAGAS 评估集(30 条人工 + 70 条 LLM 辅助)
  - `RagasCollector` + `RagasEvaluator`(DeepSeek + HuggingFace 嵌入)
  - 6 章 Markdown 报告生成器
- **P5.3 基线对比报告**
  - 五维雷达图渲染
  - `comparison_v1.md` 生成
- **P5.4 飞书前端端到端**
  - Node.js intent detection + ChatState(内存 Map,TTL 24h)
  - 飞书交互卡片(面试邀请按钮)
  - `card.action.trigger` 处理 + 面试文本中继

**关键产出**:端到端真机可跑、RAGAS runner、飞书卡片交互、`docs/demo_script.md` 答辩演示脚本。

### Week 6 · 性能优化 + 作品集整理(2026-04-19 收口)

**目标**:延迟/成本优化,作品集材料齐备。

- **P6.1 性能优化**
  - `CachedEmbedder` LRU 缓存(`OrderedDict` + `threading.Lock`,零依赖)
  - `DoubaoEmbedder` httpx.AsyncClient 复用 + `aclose()`
  - `main.py` lifespan `_close_http_singletons()` 关闭 feishu/github/embedder 单例
  - `final_synthesis` prompt 压缩(`_compact_skill_data()`,≥50% token 减量)
  - `scripts/profile_baseline.py` 基准 profile CLI
  - 16 条新单测全部通过
- **P6.3 作品集材料**
  - README(作品集入口)+ ARCHITECTURE.md + DATASETS.md + EVALUATION.md
  - comparison_v1.md + registration_form.md(200/300/500 字三版)
  - defense_deck.md(12 页 + 逐页讲稿)
  - CHANGELOG.md(6 周全程日志)
  - AI项目报告.md(本文档)

**本周不做**:LLM 批处理(interview 评分本质串行,Skill 已经 asyncio.gather 并发,没有合适靶点)。

---

## 7. 评估结果

> 所有数字均可回溯到 `python-agent/evaluation/reports/` 原始报告。

### 7.1 RAGAS 四件套(检索层)

| 指标 | 目标 | 状态 |
|---|---|---|
| Context Relevance | > 0.75 | runner 已落地,`evaluation/ragas/`(23 条单测全绿),待真机跑完出 `ragas_v1.md` |
| Context Recall | > 0.80 | 同上 |
| Faithfulness | > 0.85 | 同上 |
| Answer Relevancy | > 0.80 | 同上 |

**诚实备注**:RAGAS 评估 runner 代码已完整(`evaluation/ragas/ragas_runner.py` + `renderer.py`),23 条 pytest 全绿。真机评估需消耗 DeepSeek API 额度,当前仍在排期。未出报告前,**不宣称具体数字**。

### 7.2 Scenario A(编排层,500 条 JD 全量)

数据源:[`scenario_a_v1.md`](python-agent/evaluation/reports/scenario_a_v1.md)

| 指标 | 主图 | Baseline | 目标 | 状态 |
|---|---|---|---|---|
| Joint Accuracy(5 维全对)| 0.008 | — | > 0.90 | ❌(sub_type 词表未固化)|
| job_type Macro F1 | 0.648 | — | > 0.85 | ❌ |
| Skill Routing Macro F1 | 0.531 | — | > 0.85 | ❌ |
| **Over-invocation Rate** | **0.006** | **1.000** | < 0.10 | **✅** |
| P95 Latency | 76,438ms | 82,558ms | < 8000ms | ❌(W6 P6.1 优化中)|
| Token 降幅 | **28.1%** | — | ≥ 30% | ⚠️ 差 1.9 pp |

**Per-Skill 路由 F1**:

| Skill | Precision | Recall | F1 |
|---|---|---|---|
| en_translate | 0.968 | 0.984 | **0.976** |
| tech_stack_extract | 1.000 | 0.876 | **0.934** |
| interview_rag | 1.000 | 0.700 | **0.824** |
| gpa_check | 0.941 | 0.296 | 0.451 |
| github_scan | 0.000 | 0.000 | 0.000 |
| portfolio_check | 0.000 | 0.000 | 0.000 |

> github_scan / portfolio_check F1 为 0 的主因:500 条评估集未注入 `github_username` / `portfolio_url` 字段,should_invoke 规则拒绝触发。属评估集设计问题,不是代码逻辑问题。

**Per-Node 延迟分解**(主图 P95):

| 节点 | Mean | P95 | 占比 |
|---|---|---|---|
| parse_jd | 7,755ms | 11,963ms | 15% |
| classify_jd | 2,391ms | 3,155ms | 4% |
| invoke_skills_parallel | 7,194ms | 15,016ms | 20% |
| **final_synthesis** | **35,124ms** | **49,483ms** | **65%** |

> final_synthesis 是延迟瓶颈。W6 P6.1 已落地 prompt 压缩 ≥50% + Embedding LRU 缓存,待真机回归。

### 7.3 Interview Replay(30 对 pair)

数据源:[`replay_evaluation_v1.md`](python-agent/evaluation/reports/replay_evaluation_v1.md)

| 指标 | 目标 | 实测 | 状态 |
|---|---|---|---|
| Semantic Similarity 均值 | > 0.70 | 0.480 | ❌ |
| **Rank@3** | > 0.60 | **0.933** | **✅** |
| **Rank@5** | > 0.85 | **0.933** | **✅** |

**分 stage 表现**:

| Stage | Count | Mean Sim | Rank@3 |
|---|---|---|---|
| project_deep_dive | 7 | 0.618 | 1.000 |
| scenario | 1 | 0.487 | 1.000 |
| tech_qa | 22 | 0.435 | 0.909 |

**解读**:Bot 出题与真实追问**方向对、用词异**。Rank@K 高说明 Bot 的候选集能覆盖考点,SemSim 中等说明用词和角度差异。改进方向:对应 stage prompt 补 few-shot 示例。

### 7.4 Stage Prediction(300 条)

数据源:[`stage_prediction_v1.md`](python-agent/evaluation/reports/stage_prediction_v1.md)

| 指标 | 目标 | 实测 | 状态 |
|---|---|---|---|
| Accuracy | > 0.85 | 0.723 | ❌ |

主要混淆:`project_deep_dive → intro`(86.4%)、`scenario → tech_qa`(80%)。改进方向:predict_stage prompt 增加 1-2 个 few-shot 对话示例。

### 7.5 Checkpoint Consistency(必须 100%)

数据源:[`checkpoint_consistency_v1.md`](python-agent/evaluation/reports/checkpoint_consistency_v1.md)

| 场景 | SQLite | Postgres |
|---|---|---|
| 5 轮后 kill | ✅(450s)| ⏭️ 需 POSTGRES_TEST_URL |
| 多次 kill | ✅(~400s)| ⏭️ |
| interrupt 期间 kill | ✅(107s)| ⏭️ |
| 并发多 thread | ✅(~400s)| ⏭️ |

**6 个一致性字段**(current_stage / transcript / performance_signals / stage_round_count / stage_history / candidate_profile)**全部 100% 恢复**。

### 7.6 综合对比(主图 vs Baseline)

![五维雷达图](python-agent/evaluation/reports/figures/five_dim_radar.png)

| 维度 | 差异 |
|---|---|
| Over-invocation Rate | **-99.4 pp** |
| 总 Token 消耗 | **-28.1%** |
| 总 LLM Calls | -28.3% |
| P50 Latency | -19.4% |
| P95 Latency | -7.4% |
| 估算费用 | **-28.1%** |

详细对比见 [comparison_v1.md](python-agent/evaluation/reports/comparison_v1.md)。

---

## 8. 关键技术决策(ADR 精选)

### ADR-001:主索引选 Milvus 不选 Chroma

- **决策**:Milvus 2.4(HNSW: M=16, efC=200, ef=64)
- **理由**:Milvus 对动态字段过滤(`expr`)支持原生、集合大时性能稳定;Chroma 后置过滤在 ≥3000 向量后退化严重
- **降级**:保留 `RETRIEVAL_FALLBACK_TO_CHROMA=true`,本地无 Milvus 环境可用 Chroma 跑单测
- **代价**:多 docker 服务、多部署成本。**收益**:召回 P95 <100ms

### ADR-002:Skill 双接口(should_invoke + to_langchain_tool)

- **决策**:每个 Skill 同时实现规则层 `should_invoke` 和 LangChain Tool 导出
- **理由**:规则路由可预测、可回放、可量化;tool-calling 保留作研究路径
- **实证**:Scenario A 显示规则路由 Over-invocation 0.6%,远低于强制全调 Baseline 的 100%
- **代价**:每个 Skill 多写一个方法。**收益**:编排层可量化,不陷入"LLM 黑盒"

### ADR-003:主图与面试子图不嵌套,用 SessionContext 桥

- **决策**:两图完全独立,API 层用 Redis 桥接
- **理由**:
  - 主图一次性执行无 checkpointer,子图多轮交互需 checkpointer,运行时形态不同
  - 飞书 webhook "先 ack 再异步" 要求决定主图必须立即返回;面试"开始"是独立用户动作
  - 解耦后,两图各自评估集独立(Scenario A vs Scenario B 三件套),诊断简单
- **代价**:多一个 Redis 依赖。**收益**:图拓扑干净,评估独立

### ADR-004:LLM 后端切换 DeepSeek 不用 OpenAI

- **决策**:默认 LLM 切换为 DeepSeek(OpenAI 兼容 API,`base_url=https://api.deepseek.com/v1`,`model=deepseek-chat`)
- **理由**:国内合规、低延迟、成本降幅 ~50%(对比 OpenAI GPT-4-turbo)
- **代价**:中文语义细节上略弱于 GPT-4。**收益**:500 条全量跑得起(OpenAI 同规模成本过高)

### ADR-005:W6 不做 LLM 批处理优化

- **决策**:interview `evaluate_candidate_answer` 不批处理
- **理由**:
  - 每轮评分依赖"新用户答复到达",本质**串行**,无合法批处理窗口
  - Skill 层已用 `asyncio.gather` 做真并发,不是"串行等串行"
  - 盲目批处理会引入"等一组请求凑齐"的额外延迟
- **代价**:少一项优化项产出。**收益**:避免过度工程化,诚实记录决策过程

---

## 9. 工程化实践

### 9.1 契约驱动开发

两栈通过 OpenAPI 3.1 契约自动同步类型,CI 强制检查:

```yaml
# .github/workflows/contract-check.yml
- uv run python scripts/export_openapi.py  # Python 导出
- npm run gen:types                         # Node 生成
- git diff --exit-code contracts/ src/integrations/python-agent/generated.ts
```

**效果**:Python 改 schema 但没跑 `make contracts`,PR 直接挂。避免两边"字段改了对方不知道"的集成坑。

### 9.2 Ack-first Webhook

飞书对 webhook 回调有 3s 严格超时要求。所有 handler 必须:

1. 校验 `verificationToken`
2. `markEventProcessed(event_id)` 去重(in-memory TTL cache)
3. **`res.json({code:0})` 先返**
4. 异步 kick 真实处理(unawaited promise + 自己 catch)

这个约束强制了"webhook 层只做路由,重业务逻辑异步执行"的架构纪律。

### 9.3 X-Request-Id 跨栈追踪

`pythonAgentClient.ts` 每次调用自动生成 UUID 并设置 `X-Request-Id`。Python 中间件(`main.py::request_context_middleware`)接收后绑定到 structlog context,并在响应头回显。

**调试场景**:cross-stack 报错时,两边 log grep 同一个 UUID 即可拼完整调用链。

### 9.4 Fallback 到 Legacy 编排

`USE_PYTHON_AGENT=true` 时,任何 `PythonAgentError`(timeout/5xx/network)触发自动降级到 `orchestrator.legacy.ts`(pre-split 全 Node.js 版)。用户无感知。

**副作用**:Python 侧不直接写飞书副作用,由 Node.js 层统一落地。

### 9.5 测试分层

| 层级 | 工具 | 覆盖范围 |
|---|---|---|
| 单元测试 | pytest / vitest | 核心函数、Schema 验证 |
| 集成测试 | pytest `-m integration` | Milvus / Postgres / Redis 交互,默认跳过 |
| Checkpoint 自动化 | pytest `-m checkpoint` | SIGKILL kill-restart 场景 |
| E2E smoke | `scripts/demo_e2e.py` | 交互式演示,答辩用 |

### 9.6 Docker Compose 一键起

```bash
docker-compose up -d   # Milvus + Postgres + Redis
make dev-node          # Gateway
make dev-py            # Python Agent
```

单机全栈启动 <60s(含 Milvus 冷启动)。

---

## 10. 总结与展望

### 10.1 已达成的价值

| 类别 | 交付 |
|---|---|
| **技术能力** | RAG 混合检索 + LangGraph 四原语 + Skill 模块化 全部落地且可量化 |
| **评估严肃** | 三层评估金字塔,每一项都有 JSONL 原始数据可回溯;5 份独立评估报告 |
| **工程严肃** | 双栈 OpenAPI 契约 CI 同步 + ack-first webhook + SIGKILL 一致性 100% |
| **数据资产** | 500 条 JD + 643 条面经 + 100 条 RAGAS,合规声明完整 |
| **展示就绪** | 飞书端到端真机可跑 + 答辩脚本 + PPT 提纲 |

### 10.2 尚未达标的项(诚实列举)

1. **Joint Accuracy 0.008**:sub_type 自由文本字段的 LLM 生成近义词问题
2. **P95 Latency 76s**:final_synthesis 节点占 65%,W6 P6.1 已落地代码待真机回归
3. **Stage Accuracy 72.3%**:project_deep_dive / scenario 特征接近,需 few-shot
4. **Replay SemSim 0.48**:Bot 用词与真实面试官角度有差异(但 Rank@K 高 → 方向对)
5. **Token 降幅 28.1%**:差 1.9 pp(W6 prompt 压缩叠加后预计破 40%)
6. **RAGAS 报告**:runner 已就绪,真机评估排期中

### 10.3 未来三个方向(V2)

**方向 1 · 多前端扩展**

飞书 → 微信 / 钉钉 / Slack。业务图(主图 + 面试子图)不变,只新增 Gateway 适配层。证明本架构"面向 IM 协议解耦"的设计价值。

**方向 2 · HR 视角反转(对齐 OpenClaw)**

当前是候选人视角,反转为 HR 视角:

- 同一份 JD,从"候选人准备什么" → "HR 应考察什么"
- 复用现有 RAG(jd_kb + interview_kb)+ Skill 生态
- 反转 prompt template,生成面试官题库 / 评估 rubric
- 对齐 OpenClaw 课题一"企业办公知识整合与分发"的深度

**方向 3 · MCP Protocol 兼容**

把 6 个 Skill 导出为 Model Context Protocol tool,成为其他 Agent 系统可调用的 capability provider。扩大生态位置,不只是独立 Agent。

### 10.4 结语

6 周从零做到端到端的 AI Agent 工程,**最大的收获不是某个指标漂亮,而是建立起"能力 → 指标 → 数据"的对齐链条**。每一项功能都对应一个可测指标;每一个指标都落到具体 JSONL 数据;每一份数据都可以被外部评委拿去复现。

这套纪律让项目在答辩场景下可辩、在生产场景下可维护、在科研场景下可扩展 —— 这才是 LangGraph / RAG / 评估框架这类"重工程"技术应有的样子。

---

## 11. 附录

### 11.1 关键文档导航

| 文档 | 用途 |
|---|---|
| [README.md](README.md) | 作品集入口,30 秒过项目全貌 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 双栈理由、LangGraph 四能力映射、ADR |
| [DATASETS.md](DATASETS.md) | 3 数据集 schema、合规、复现命令 |
| [EVALUATION.md](EVALUATION.md) | 三层评估方法、指标口径、复现命令 |
| [CHANGELOG.md](CHANGELOG.md) | 6 周进度日志 |
| [docs/e2e_flow.md](docs/e2e_flow.md) | JD → 面试端到端时序图 |
| [docs/demo_script.md](docs/demo_script.md) | 答辩演示分步脚本 |
| [docs/defense_deck.md](docs/defense_deck.md) | 12 页 PPT 提纲 + 讲稿 |
| [docs/registration_form.md](docs/registration_form.md) | 报名表三版文案 |

### 11.2 评估报告清单

- [scenario_a_v1.md](python-agent/evaluation/reports/scenario_a_v1.md) · 编排层,500 条全量
- [replay_evaluation_v1.md](python-agent/evaluation/reports/replay_evaluation_v1.md) · Interview Replay 30 对
- [stage_prediction_v1.md](python-agent/evaluation/reports/stage_prediction_v1.md) · 阶段推进 300 条
- [checkpoint_consistency_v1.md](python-agent/evaluation/reports/checkpoint_consistency_v1.md) · 断点续聊 4 场景
- [comparison_v1.md](python-agent/evaluation/reports/comparison_v1.md) · 主图 vs Baseline 五维对比

### 11.3 技术栈速览

| 类别 | 选型 |
|---|---|
| 语言 | Python 3.11 / TypeScript / Node.js 18 |
| Web 框架 | FastAPI / Express |
| AI 框架 | LangChain ≥0.2 / LangGraph ≥0.2 |
| 向量库 | Milvus 2.4 (HNSW) · Chroma 降级 |
| 稀疏检索 | BM25Okapi + jieba + TECH_TERMS |
| Embedding | BGE-M3(本地)/ DeepSeek(远程)· dim=1024 |
| Rerank | BGE cross-encoder(可选) |
| Checkpointer | AsyncSqliteSaver / AsyncPostgresSaver |
| SessionContext | Redis 7 Alpine,TTL 24h |
| LLM | DeepSeek-chat(OpenAI 兼容 API) |
| 评估 | RAGAS + 自研 Scenario A/B evaluator |
| 契约 | OpenAPI 3.1 + openapi-typescript |
| 部署 | Docker Compose 一键起全栈 |

### 11.4 可复现命令(全套)

```bash
# 1. 环境搭建
git clone <repo-url> && cd jobpilot-feishu
cp .env.example .env
cp python-agent/.env.example python-agent/.env
docker-compose up -d
make dev-node   # terminal 1
make dev-py     # terminal 2

# 2. 数据集构建(可选,已提供 labeled jsonl)
cd knowledge-base
kb-build crawl --source hf --path ~/Downloads/jobs.csv
kb-build clean / llm-annotate / import-review

# 3. 灌库
docker compose --profile ingest up --build kb-ingester

# 4. 全套评估
cd python-agent
uv run python scripts/run_scenario_a.py --mode main --out evaluation/runs/main_v1.jsonl
uv run python scripts/run_scenario_a.py --mode baseline --out evaluation/runs/baseline_v1.jsonl
uv run python scripts/render_scenario_a_report.py --main ... --baseline ...
uv run python scripts/run_interview_replay.py --n 30
uv run python scripts/run_stage_eval.py --n 300
UV_PROJECT_ENVIRONMENT=/tmp/jobpilot-venv uv run pytest tests/checkpoint/ -m checkpoint
uv run python scripts/run_ragas_eval.py build / collect / evaluate / render
```

### 11.5 作者与致谢

- **作者信息**:见 `docs/registration_form.md`
- **License**:代码 MIT;数据集仅限非商业研究评估
- **参赛**:飞书校园挑战赛(开放创新赛道)
- **致谢**:LangChain / LangGraph / Milvus / RAGAS / 飞书开放平台团队的开源工作
