# Changelog

All notable changes to this project are documented here.

---

## Week 6 — 2026-04-19(收口周)

### P6.1 — 性能优化(Embedding 缓存 + prompt 压缩 + HTTP 连接池)

- `retrieval/embedding.py`:新增 `CachedEmbedder`(LRU wrapper,`collections.OrderedDict` + `threading.Lock`,`max_size` 由 `embedding_cache_size` 控制,默认 10000);`DoubaoEmbedder` 重构,`httpx.AsyncClient` 复用(双检查 `_get_client()` + `asyncio.Lock` 一次性初始化)+ `aclose()`
- `config.py`:新增 `embedding_cache_enabled` / `embedding_cache_size` 两项;LLM 默认切换为 `deepseek-chat`(`llm_api_base_url=https://api.deepseek.com/v1`)
- `graphs/prompts/final_synthesis.py`:新增 `_compact_skill_data()`,按 Skill 名规则压缩 skill_data(tech_stack_extract 仅保留 8 primary + 5 preferred name;interview_rag 仅保留 top 5 question + intent;en_translate 翻译文本裁至 600 字;未知 skill 透传),prompt 压缩 ≥50%
- `main.py`:lifespan 新增 `_close_http_singletons()`,关闭 feishu_proxy / github_client / embedder 三个全局单例,每个独立 try/except 隔离失败
- `scripts/profile_baseline.py`:基准 profile CLI(`--label/--n/--concurrency/--dataset/--compare`),聚合 per-node / per-skill P50/P95/P99 延迟,输出 `docs/performance/runs/<label>.{raw.jsonl,agg.json,md}`
- 新增测试:`tests/retrieval/test_cached_embedder.py`(8 条,LRU eviction / 并发安全 / aclose 转发)、`tests/graphs/test_final_synthesis_compact.py`(8 条,含 ≥50% 压缩率断言)
- LLM 批处理(interview `evaluate_candidate_answer`):评估后判定无可批目标 —— 每轮评分依赖新用户答复,本质串行;Skill 侧已通过 `asyncio.gather` 并发。**不实施,已记录原因。**

### P6.3 — 作品集材料整理

- `README.md`:改为作品集入口(亮点指标表 + 架构缩略图 + 文档导航)
- `ARCHITECTURE.md` 新建:双栈理由 + LangGraph 四能力 + 3 条 ADR
- `DATASETS.md` 扩写:三数据集 + 合法性声明 + 复现命令 + 数据血缘
- `EVALUATION.md` 新建:三层评估金字塔 + 所有指标真实数字 + 复现命令
- `evaluation/reports/comparison_v1.md` 新建:主图 vs Baseline 五维对比报告(雷达图嵌入)
- `docs/registration_form.md` 新建:200 / 300 / 500 字三版报名表文案
- `docs/defense_deck.md` 新建:12 页答辩 PPT 提纲 + 逐页讲稿

---

## Week 5 — 2026-04-19

### P5.1 — 主图挂载面试子图（Redis 桥接）

- `api/schemas.py`：`InterviewInvitation` 模型 + `JDRoutingResults.interview_invitation` 扩展；`UserContext.feishu_chat_id` 新增
- `graphs/nodes/final_synthesis.py`：`_should_invite_interview()` 规则（5 条）+ `_build_interview_invitation()` 构造邀请对象
- `orchestration/session_context.py`：`SessionContextStore`（Redis `setex` TTL 24h）+ `get_session_store()` 单例
- `api/jd_routing.py`：路由完成后将 session context 写入 Redis（以 `feishu_chat_id` 为键）
- `api/interview.py`：`/interview/start` 支持从 Redis session context 自动补齐 company/position
- `graphs/interview/nodes/init.py`：从 `metadata.source_session_context` 读取 jd_summary/parsed_jd
- `docker-compose.yml`：新增 Redis 7 Alpine 服务（:6379）
- `pyproject.toml`：新增 `redis[asyncio]>=5.0` 依赖
- 新增测试：`tests/orchestration/test_invitation_rules.py`（11 条）、`test_session_context.py`（5 条）、`test_e2e_main_to_interview.py`（5 条集成测试）
- 新增文档：`docs/e2e_flow.md`（时序图）、`scripts/demo_e2e.py`（交互演示）

### P5.2 — RAGAS 四件套评估

- `skills/interview_rag/schemas.py`：`InterviewRagData.raw_retrieved_texts` 新增字段
- `skills/interview_rag/index.py`：将原始检索文本写入 `raw_retrieved_texts`
- `evaluation/ragas/schema.py`：`RagasExample / RagasResult / RagasAggregate / RagasCompanyMetric` 数据模型
- `evaluation/ragas/dataset_builder.py`：分层抽样（按 job_type）+ LLM 辅助 ground_truth 生成
- `evaluation/ragas/ragas_runner.py`：`RagasCollector`（图运行 + checkpoint）+ `RagasEvaluator`（doubao LLM + HuggingFace 嵌入）
- `evaluation/ragas/metrics_wrapper.py`：`safe_float()` NaN 处理 + `aggregate_results()` 分组聚合
- `evaluation/ragas/renderer.py`：6 章 Markdown 报告 + 分布直方图 + 公司柱状图
- `scripts/run_ragas_eval.py`：`build / collect / evaluate / render` 四子命令 CLI
- 新增测试：`tests/ragas/test_dataset_builder.py`（10 条）、`test_metrics_wrapper.py`（9 条）、`test_renderer.py`（4 条）

### P5.3 — 基线对比报告

- 复用 `scripts/render_scenario_a_report.py` 生成 `evaluation/reports/comparison_v1.md`
- 五维雷达图已存在：`evaluation/reports/figures/five_dim_radar.png`（111KB）
- 新增测试：`tests/comparison/test_radar_scores.py`（4 条，验证低延迟/低成本分数边界）

### P5.4 — 飞书前端端到端打通

**Python Agent（P5.1 已覆盖）**
- JD 分析结果附带 `interview_invitation`，包含公司/岗位/CTA 文本/session seed

**Node.js Gateway**
- `src/services/intent-detector.service.ts`：`detectIntent(text, isInInterview)` → `jd_routing | interview_reply | general_chat`
- `src/services/chat-state.service.ts`：内存 `ChatStateService`（TTL 24h，支持 start/end/prune）
- `src/integrations/feishu/card-builder.ts`：`buildInterviewInvitationCard()` 生成带按钮的交互卡片
- `src/controllers/feishu-event.controller.ts`：
  - 新增 `card.action.trigger` 事件路由（调用 `interview/start`，发送面试开场白）
  - `handleMessageEvent()` 插入意图判断（面试中继 / 通用提示 / JD 路由）
  - JD 路由完成后自动发送面试邀请卡片
- `src/services/orchestrator.service.ts`：提取 `interview_invitation`，传递 `feishu_chat_id` 给 Python Agent
- `src/routes/internal.routes.ts`：`POST /internal/feishu/bitable/query` 真实实现（调用 `searchRecordsInTable`）
- `src/constants/index.ts`：新增 `FEISHU_EVENT_TYPE_CARD_ACTION`
- `src/types/index.ts`：新增 `InterviewInvitation`、`FeishuCardActionBody`、`OrchestratorResult.interviewInvitation`
- 新增测试：`src/services/__tests__/intent-detector.test.ts`（6 条）、`chat-state.test.ts`（5 条）
- 新增文档：`docs/demo_script.md`（完整答辩演示脚本）

---

## Week 4 — 2026-04-19

### Added

**P4.1 面试子图**
- `graphs/interview/`：`InterviewState` TypedDict + 6 个面试节点（init / ask_question / evaluate_answer / provide_feedback / summarize_stage / generate_report）
- 5 个面试阶段：intro / project_deep_dive / tech_qa / scenario / closing
- LangGraph `interrupt()` 断点：每问题后等待用户输入
- `POST /api/v1/agent/interview/start`：启动面试会话
- `POST /api/v1/agent/interview/resume`：提交回答并获取下一题
- `GET /api/v1/agent/interview/{session_id}/status`：查询会话状态

**P4.2 Replay & Stage 评估**
- `evaluation/runners/replay_runner.py`：Replay 评估（从真实 transcript 重放，无 LLM 调用）
- `evaluation/runners/stage_eval_runner.py`：Stage 评估（单阶段精细化指标）
- `scripts/run_interview_replay.py`：Replay CLI
- `scripts/run_stage_eval.py`：Stage 评估 CLI

---

## Week 3 — 2026-04-19

### Added

**P3.1a Skill 基础设施**
- `skills/base.py`：`SkillBase` 抽象基类（双接口：`should_invoke` + `invoke`）
- `skills/registry.py`：单例注册表，支持依赖拓扑排序
- `skills/dispatcher.py`：路由决策，基于 JDContext 批量判断 Skill 调用
- `skills/llm_skill_base.py`：LLM Skill 辅助基类，封装重试、结构化输出
- `skills/errors.py`：Skill 错误层级（Timeout / Input / External / LLM）
- `GET /api/v1/skills`：调试端点，列出所有已注册 Skill 及元数据

**P3.1b LLM Skills（3 个）**
- `tech_stack_extract`：提取技术栈标签（Tech 岗位）
- `gpa_check`：校招 GPA 门槛检验
- `en_translate`：英文 JD 翻译

**P3.1c 外部 Skills（3 个）**
- `interview_rag`：复用 Week 2 RAG 层，生成面试准备建议
- `portfolio_check`：通过 Node.js callback 调飞书文档，验证作品集
- `github_scan`：接入 GitHub API，分析高级工程师 GitHub 档案

**P3.2 LangGraph 主图**
- `graphs/state.py`：`JDRoutingState` TypedDict，Annotated reducer 支持并发写入
- 6 个图节点：`parse_jd` / `classify_jd` / `dispatch_skills` / `invoke_skills_parallel` / `merge_outputs` / `final_synthesis`
- 条件边：`dispatch_skills` → invoke（有 Skill） / skip（无 Skill）
- `invoke_skills_parallel`：`asyncio.gather` 真并发执行
- `POST /api/v1/agent/jd-routing`：主图真实调用入口（替代 W1 stub）
- `docs/jd_routing_graph.mmd`：图拓扑 Mermaid 可视化

**P3.3 场景 A 评估**
- 500 条 JD 全量运行主图评估（`evaluation/runs/main_v1.jsonl`）
- 500 条 JD 全量运行 Baseline 评估（`evaluation/runs/baseline_v1.jsonl`）
- 9 张指标图（混淆矩阵 × 5 + 路由 F1 + 延迟分布 + 成本对比 + 五维雷达图）
- `evaluation/reports/scenario_a_v1.md`：完整 6 章评估报告，含 6 条 bad case 分析

---

## Week 2 — 2026-04

### Added

- RAG 检索层：BM25Okapi（jieba + TECH_TERMS） + Milvus/Chroma 混合检索，RRF 融合，BGE 交叉编码重排
- 标注数据集：500 条 `jd_labeled.jsonl`，含 5 维分类标签
- LLM 标注辅助：`jd_llm_labeled.jsonl`

---

## Week 1 — 2026-04

### Added

- Python FastAPI 服务初始化（LangGraph + Pydantic v2 schema）
- OpenAPI 契约驱动：`contracts/openapi.json` + `src/integrations/python-agent/generated.ts`
- Node.js Gateway：Feishu webhook 接入，ack-first 异步处理，双编排器 fallback
- `/internal/feishu/docs/read`：飞书文档读取 callback（Python → Node）
- 简历 PDF 摄取：`resumeIngestionService`
