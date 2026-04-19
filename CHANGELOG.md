# Changelog

All notable changes to this project are documented here.

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
