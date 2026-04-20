# JobPilot Agent · 技术架构

本文档解释**为什么**系统长这样,而不仅仅是它长什么样。实现细节请直接读源码或 [contracts/openapi.json](contracts/openapi.json)。

---

## 1. 一图看懂

```text
┌────────────────────────────────────────────────────────────────────┐
│                        飞书开放平台                                  │
│            (IM / 多维表格 / 云文档 / Task)                           │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ Webhook / OpenAPI
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│   Node.js Gateway (Express + TypeScript, port 3000)                │
│                                                                    │
│   ┌──────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│   │  Webhook     │→ │  Orchestrator   │→ │  Feishu Integration │ │
│   │  Controller  │  │  (router+fallbk)│  │  (bitable/doc/task) │ │
│   └──────────────┘  └────────┬────────┘  └─────────────────────┘ │
│          ▲                   │ HTTP (X-Request-ID)                │
│          │                   ▼                                    │
│          │          pythonAgentClient.ts ◀── generated.ts        │
│          │                   │                  ▲                 │
│          │   /internal/feishu/* (X-Internal-Secret)              │
│          └───────────────────┼──────────────────┘                 │
└──────────────────────────────┼─────────────────────────────────────┘
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│   Python Agent (FastAPI + LangGraph, port 8001)                    │
│                                                                    │
│   ┌────────────────┐     ┌─────────────────────────────────────┐ │
│   │ /jd-routing    │────▶│      JD Routing Graph (主图)         │ │
│   │                │     │ parse → classify → dispatch →        │ │
│   │                │     │ invoke_skills_parallel → merge →     │ │
│   │                │     │ final_synthesis(+ invite rule)       │ │
│   └────────────────┘     └───────────────┬─────────────────────┘ │
│                                          │ SessionContext(Redis) │
│   ┌────────────────┐     ┌──────────────▼──────────────────────┐ │
│   │ /interview/*   │────▶│   Interview Subgraph (面试子图)       │ │
│   │ (interrupt)    │     │ intro → project → tech_qa →          │ │
│   │                │     │ scenario → reverse → closing         │ │
│   └────────────────┘     │ + evaluate → report                  │ │
│                          └───────────────┬──────────────────────┘ │
│                                          │ Checkpointer           │
└──────────────────────────────────────────┼─────────────────────────┘
                                           ▼
                         ┌─────────────┬──────────────┬────────────┐
                         │   Milvus    │   Postgres   │   Redis    │
                         │ (jd_kb /    │ (checkpoints)│ (session_  │
                         │ interview_kb│              │  context)  │
                         │ user_kb)    │              │            │
                         └─────────────┴──────────────┴────────────┘
```

## 2. 为什么选双栈架构?

### 2.1 三个方案对比

| 方案 | 优点 | 致命缺点 |
|---|---|---|
| 纯 Node.js | 飞书 SDK 一等公民 | LangChain TS / LangGraph TS 成熟度落后 Python 约半年,RAGAS 无 TS 版 |
| 纯 Python | AI 生态完整 | 飞书 SDK 覆盖不全,Webhook 稳定性差 |
| **双栈(本项目)** | 各用所长,边界清晰 | 多一次 HTTP 跳转(本地 localhost,~2-5ms) |

### 2.2 黄金法则

> **Node.js 只做"协议翻译"和"副作用",Python 做所有"智能决策"**

这条规则把架构边界划死,避免两边都想管同一件事:

- 飞书 webhook 解析、`bitable` 写入、卡片渲染、PDF 简历摄取 → **Node.js**
- JD 解析、分类、Skill 路由、LLM 合成、RAG 检索、面试编排 → **Python**

Python 想写飞书?必须通过 `POST /internal/feishu/*`(Node.js 暴露、`X-Internal-Secret` 守门)。Python 不直接拥有飞书 token。

### 2.3 契约驱动同步类型

源头是 Python 的 Pydantic v2 schema,经由 `scripts/export_openapi.py` 导出到 `contracts/openapi.json`,再用 `openapi-typescript` 生成 `src/integrations/python-agent/generated.ts`:

```
python-agent/src/jobpilot_agent/api/schemas.py
        │ uv run python scripts/export_openapi.py
        ▼
contracts/openapi.json
        │ npm run gen:types
        ▼
src/integrations/python-agent/generated.ts
```

`.github/workflows/contract-check.yml` 会在 CI 中同时跑这两步,检查是否有漂移 —— Python 改了 schema 但没跑 `make contracts`,PR 直接挂。

---

## 3. LangGraph 的四大能力,我们全用到了

LangGraph 相对于"直接调 LLM"的优势在于**四个原语**,我们挑业务场景把每一个都用一遍:

| 能力 | 用在哪 | 源码位置 |
|---|---|---|
| **分支**(Conditional Edges) | 主图 `dispatch_skills` 节点根据分类结果选择调用哪些 Skill | `graphs/main_graph.py` |
| **循环**(Cyclic Graph) | 面试子图 `project_deep_dive` / `tech_qa` 等阶段自环 2-5 轮 | `graphs/interview/interview_subgraph.py` |
| **中断**(interrupt) | 面试等待用户作答时挂起,`graph.ainvoke(Command(resume=...))` 恢复 | `graphs/interview/nodes/base.py:68` |
| **持久化**(Checkpointer) | `AsyncSqliteSaver` / `AsyncPostgresSaver` 保证 SIGKILL 后续聊一致性 | `graphs/interview/checkpointer.py` |

### 关键取舍:两图不嵌套

主图(JD 路由)和面试子图是**两张独立的 LangGraph**,不通过 LangGraph 原生 subgraph 拼接。

- **原因**:主图一次性跑完(无 checkpointer),子图多轮 + 持久化(有 checkpointer)。二者生命周期完全不同。
- **桥接**:API 层在主图结果里附加 `InterviewInvitation`,并把 `session_context` 写入 Redis(key=`session_context:{feishu_chat_id}`, TTL=24h);子图在 `/interview/start` 时从 Redis 读,补齐 company/position。

时序图:[docs/e2e_flow.md](docs/e2e_flow.md)。

---

## 4. Skill 模块化与双接口

六个 Skill(`tech_stack_extract / gpa_check / en_translate / interview_rag / portfolio_check / github_scan`)每个都实现**双接口**:

- `should_invoke(ctx: JDContext) -> bool`:业务层路由决策,纯规则、可预测。
- `to_langchain_tool()`:对外暴露为 LangChain Tool,保留"LLM tool-calling"的备选路径。

**为什么双接口**:校园挑战赛期望 6 周稳定出结果,规则路由比 LLM tool-calling 成本低、延迟稳定、可量化。Scenario A 评估证明规则路由 Over-invocation 0.6%,而 Baseline 强制全调是 100%(见 [scenario_a_v1.md](python-agent/evaluation/reports/scenario_a_v1.md) §2)。

---

## 5. 通信协议选型

- **HTTP REST(主调用)**:JSON + UTF-8,`/jd-routing` 同步返回,`/interview/*` 通过 `interrupt` 轮询恢复。
- **拒绝 gRPC**:学习成本超过收益(校内评委可能没装 protoc,调试 curl 一把梭香)。
- **拒绝 MQ**:同步交互场景过度设计。面试互动必须立即响应。
- **拒绝 SSE 流式**:首版先追求正确性,SSE 留待未来演进。

每个跨栈请求强制 `X-Request-Id`(Node 生成,Python 透传并回显),调试时两边 log 搜同一 UUID 即可拼出完整调用链。

---

## 6. RAG 检索层

三库独立部署,走统一 Retriever 接口:

| Collection | 规模 | 动态字段 | 典型过滤 |
|---|---|---|---|
| `jd_kb` | ≥1500 chunk(500 JD) | `job_type/sub_type/level/locale/channel` | `job_type=tech` |
| `interview_kb` | ≥3000 turn(643 面经) | `role/stage/level/company/year` | `stage=tech_qa` |
| `user_kb` | ≥20 section(4 简历) | `user_id/section` | `user_id=u_default` |

**混合检索**:
1. BM25Okapi(jieba 分词 + `TECH_TERMS` 自定义词典)做关键词召回
2. Milvus HNSW(BGE-M3 或 Doubao embedding,dim=1024)做向量召回
3. 自实现 `RRFRanker` 融合(`k=60` 默认)
4. 可选 BGE cross-encoder 重排

**降级**:`RETRIEVAL_FALLBACK_TO_CHROMA=true` 时,Milvus 不可达自动切换本地 Chroma,便于开发调试。

详细调优参数与推理流程:[python-agent/src/jobpilot_agent/retrieval/README.md](python-agent/src/jobpilot_agent/retrieval/README.md)。

---

## 7. 部署方案(三档)

- **Level 1 · 比赛演示(已实现)**:`docker-compose up -d` 单机全栈,含 Milvus + Postgres + Redis。
- **Level 2 · 生产目标**:Node.js / Python 独立部署,Milvus 集群化,LangSmith tracing 接入。
- **Level 3 · 长期愿景**:LangGraph Platform 托管,Skill 可热部署。

---

## 8. 关键技术决策记录(ADR)

### ADR-001:为什么选 Milvus 不选 Chroma 作主索引?

- **背景**:项目早期用 Chroma 足以跑通 demo,但上 500 条 JD + 643 条面经后性能下滑。
- **决策**:主索引切换到 Milvus 2.4(HNSW: M=16, efConstruction=200, ef=64)。
- **理由**:Milvus 对动态字段(`job_type/level` 等过滤器)支持更好,支持 `expr` 条件下的向量召回,而 Chroma 过滤路径走后置过滤,大集合下退化严重。
- **降级**:保留 `RETRIEVAL_FALLBACK_TO_CHROMA=true`,本地无 Milvus 环境可跑单测。
- **代价**:多一个 docker 服务、多一份文档、部署成本略升。收益:召回延迟 P95 稳定在 <100ms。

### ADR-002:Skill 双接口(should_invoke + to_langchain_tool)

- **背景**:LangChain 生态推崇 LLM tool-calling,但 tool-calling 的过度调用率高。
- **决策**:每个 Skill 同时实现"规则层 `should_invoke`"和"LangChain Tool 导出"两个接口;生产路径默认走规则层,tool-calling 作为研究/演进备选。
- **实证**:Scenario A 评估显示规则路由 Over-invocation Rate 0.6%,远低于强制全调 Baseline 的 100%。
- **代价**:每个 Skill 多写一个 `should_invoke` 方法。收益:路由可预测、可回放、可量化。

### ADR-003:主图与面试子图不嵌套,用 SessionContext(Redis)桥接

- **背景**:直觉上两图应该用 LangGraph 原生 subgraph 拼成一张大图。
- **决策**:**不嵌套**,两图完全独立,API 层用 Redis 桥接。
- **理由**:
  - 主图一次性执行,无需 checkpointer;子图多轮交互,必须 checkpointer。两者的运行时形态完全不同,硬塞进一张图会污染 state 定义。
  - 飞书 webhook "先 ack 再异步处理" 的要求决定了主图跑完必须立即返回;面试"开始"则是独立的用户动作,两者时间上可能相隔几分钟到几小时。
  - 两图解耦后,各自的评估(Scenario A vs Scenario B/Replay/Stage)完全独立,诊断更简单。
- **代价**:多一个 Redis 依赖。收益:评估集独立、测试独立、图拓扑干净。

---

## 9. 关键 API 契约(速览)

| Endpoint | Method | 用途 | Owner |
|---|---|---|---|
| `/api/v1/agent/jd-routing` | POST | JD 路由分析主入口 | Python |
| `/api/v1/agent/interview/start` | POST | 启动面试会话 | Python |
| `/api/v1/agent/interview/resume` | POST | 提交答复并续聊 | Python |
| `/api/v1/agent/interview/{thread_id}/status` | GET | 查询面试会话状态 | Python |
| `/api/v1/skills` | GET | 调试:列出已注册 Skill | Python |
| `/internal/feishu/docs/read` | POST | Python → Node 读飞书文档 | Node.js |
| `/internal/feishu/bitable/query` | POST | Python → Node 查多维表格 | Node.js |

完整字段定义详见 [contracts/openapi.json](contracts/openapi.json)。

---

## 10. 数据流:一条 JD 在系统里如何流动

1. 飞书用户在群里粘贴 JD → `POST /webhook/feishu`(Node.js,ack-first,3s 内必须 200)
2. Node.js `FeishuEventController` 校验 token + 事件去重(in-memory TTL cache)+ 异步调度
3. `orchestratorService.execute(jdText)` → `pythonAgentClient.postJdRouting()`(带 `X-Request-Id` UUID)
4. Python FastAPI 接收 → `JD Routing Graph.ainvoke(state)`
5. 主图 6 节点顺序:parse_jd → classify_jd → dispatch_skills(conditional)→ invoke_skills_parallel(asyncio.gather)→ merge_outputs → final_synthesis
6. final_synthesis 后执行 `_should_invite_interview()` 规则 → 如命中,附加 `InterviewInvitation` + 写 Redis `session_context:{feishu_chat_id}`
7. Python 返回 `JDRoutingResponse` → Node.js mapping 为 `OrchestratorResult`
8. Node.js 执行副作用:回复卡片(含"开始面试"按钮)+ 写多维表格 + 生成准备文档
9. 用户点"开始面试" → `card.action.trigger` → `POST /interview/start`(thread_id=feishu_chat_id)→ Python 从 Redis 读 session_context → 启动面试子图
10. 面试子图 interrupt/resume 循环 → 5 阶段跑完 → 生成 `InterviewReport` → 回写飞书

时序图完整版:[docs/e2e_flow.md](docs/e2e_flow.md)。
