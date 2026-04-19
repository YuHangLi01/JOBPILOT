# Changelog

All notable changes to the Python Agent service are documented here.

---

## [Unreleased] — P4.3 阶段预测准确率 + 断点续聊一致性

### Added
- `InterviewerCore.predict_stage()`: 基于对话历史的 6 类阶段分类（intro / project_deep_dive / tech_qa / scenario / reverse / closing）
- `src/jobpilot_agent/evaluation/stage/`: 阶段预测准确率评估模块（runner / metrics / renderer / loader / sampling）
- `scripts/run_stage_eval.py`: 阶段评估 CLI（run / render / run-and-render 三个子命令）
- `GET /interview/{thread_id}/_debug_state`: 调试端点，返回完整 LangGraph state（dev 环境可用）
- `tests/checkpoint/`: SQLite + Postgres kill-restart 一致性测试套件（各 4 个场景）
- `tests/checkpoint/helpers/`: process_manager / mock_client / state_comparator 工具类
- `.github/workflows/checkpoint-test.yml`: CI 自动化断点续聊测试（SQLite + Postgres service）
- `evaluation/reports/checkpoint_consistency_v1.md`: 断点续聊一致性验收报告
- `pytest` marker `checkpoint`: 隔离子进程测试，`-m checkpoint` 显式启用

### Design Decisions
- `_debug_state` 端点检查 `app_env != "prod"` 而非新增 "test" Literal，保持类型兼容
- 子进程测试继承父进程 env（透传 `LLM_API_KEY`），并覆盖 `RETRIEVAL_FALLBACK_TO_CHROMA=true` 规避 Milvus 依赖
- `_deep_equal` 自实现（不用 `==`）：Turn list 按 turn_id 排序后字段逐一比对，避免 datetime 序列化不一致

---

## [Unreleased] — P4.2 Interview Replay 评估

### Added
- `src/jobpilot_agent/evaluation/replay/`: Replay 评估模块（sampling / runner / metrics / renderer / schema）
- `scripts/run_interview_replay.py`: Replay 评估 CLI（run / render / run-and-render）
- `evaluation/runs/`: 评估结果 JSONL（smoke_3 / smoke_5 / main_v1 / baseline_v1 / replay_v1）
- `evaluation/reports/interview_replay_smoke.md`: 30 对 smoke 评估报告
- `evaluation/reports/replay_evaluation_v1.md`: 500 对全量评估报告
- `evaluation/reports/figures/`: similarity histogram / rank@k bar / per-stage radar 等 PNG

### Design Decisions
- `_SIMILARITY_THRESHOLD = 0.35`（BGE-M3 L2-norm cosine 空间；OpenAI 级 embedding 用 0.75）；0.70 mean_sim 目标为 API embedding 设定，BGE-M3 本地 baseline ≈ 0.48，属已知限制
- 复用 `InterviewerCore.generate_top_k_questions(k=5)` 而非重写出题 prompt
- 所有 5 个 stage prompt 在 `top_k` 参数存在时切换为 `{"questions": [...]}` 多问题格式

---

## [Unreleased] — P4.1c 子图组装 + API

### Added
- `src/jobpilot_agent/graphs/interview/interview_subgraph.py`: `build_interview_subgraph()` + `compile_interview_subgraph()`，含 3 个条件回边（project_deep_dive / tech_qa / scenario 循环）
- `POST /api/v1/agent/interview/start`: 初始化面试会话，返回面试官首问
- `POST /api/v1/agent/interview/resume`: 用户回答后推进图，返回下一个面试官问题
- `GET /api/v1/agent/interview/{thread_id}/status`: 查询会话状态（阶段 / 轮次 / transcript 长度）
- `scripts/demo_interview.py`: 命令行交互式面试 demo（httpx 直连 API）
- `scripts/export_interview_graph.py`: 导出 Mermaid 源文件 + PNG（via Mermaid.ink API）
- `docs/interview_subgraph.mmd` / `docs/interview_subgraph.png`: 状态转移图可视化

---

## [Unreleased] — P4.1b 5 阶段节点

### Added
- 10 个面试图节点：`init / intro / project_deep_dive / tech_qa / scenario / reverse / closing / evaluate_performance` + 3 个 judge 节点
- `nodes/base.py`: `run_interview_turn()` —— 出题 → interrupt 等待用户 → 评估回答，被 intro / project_deep_dive / tech_qa / scenario 复用
- `nodes/reverse.py`: 角色反转逻辑，候选人发问 3 轮后自动进入 closing
- 6 个 stage prompt 文件（含 few-shot 示例）：intro（ByteKV 案例）/ tech_qa（HashMap vs TreeMap / 10B 用户消息系统）/ evaluate（JSON 片段示例）等
- 节点级单测 9 个（`tests/graphs/interview/test_nodes.py`）

---

## [Unreleased] — P4.1a 面试子图基础设施

### Added
- `src/jobpilot_agent/graphs/interview/state.py`: `InterviewState` TypedDict，5 个自定义 reducer（`_append_turns` / `_inc_round` / `_dict_merge` 等）
- `src/jobpilot_agent/graphs/interview/checkpointer.py`: 双 backend（AsyncSqliteSaver / AsyncPostgresSaver），FastAPI lifespan 管理，`CHECKPOINTER_BACKEND` env 切换
- `src/jobpilot_agent/graphs/interview/interviewer_core.py`: `InterviewerCore` —— `generate_next_question` / `generate_top_k_questions` / `evaluate_candidate_answer` / `judge_should_continue` / `predict_stage`
- `src/jobpilot_agent/graphs/interview/profile_builder.py`: 简历解析 → `CandidateProfile`，空 KB 时返回 "未提供简历信息" 占位
- `src/jobpilot_agent/graphs/interview/transcript.py`: `format_transcript_for_llm` / `get_last_candidate_turn` / `count_stage_turns` / `next_turn_id` 4 个纯函数
- 基础设施单测 16 个（`tests/graphs/interview/test_infrastructure.py`）
