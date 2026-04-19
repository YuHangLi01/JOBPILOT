# Checkpoint Kill-Restart 一致性测试

## 业务价值

模拟面试是一个**长会话**任务：用户可能在面试进行到一半时关闭飞书（进程崩溃）。
如果状态不持久化，重新进入时面试会从头开始——这是不可接受的用户体验。

本测试套件用 **SIGKILL 硬杀进程** 的方式验证：
1. 状态在持久化层（SQLite / PostgreSQL）中完整保存
2. 重启后能 100% 恢复，不丢失任何对话轮次
3. 从中断点继续对话能正常进行到结束

## 测试架构

```
测试进程 (pytest)
    │
    ├── Phase 1：subprocess.Popen 启动 uvicorn
    │           │
    │           └── 用 httpx 模拟用户 API 调用（start / resume）
    │
    ├── process.kill()  ← SIGKILL，不给任何清理机会
    │
    └── Phase 2：再次 Popen 启动（相同 SQLite 文件）
                │
                ├── aget_state() 读取 LangGraph checkpoint
                ├── 比对 6 个严格字段
                └── 继续调用 resume 直到 state=completed
```

关键设计原则：
- **不用 in-process TestClient**：必须是真实的 OS 进程，才能测 SIGKILL 场景
- **SIGKILL 而非 SIGTERM**：SIGTERM 允许进程清理，不是最激进的场景
- **立即重启**：不等待，测恶劣条件下的恢复能力

## 本地运行

```bash
# SQLite（无需额外依赖）
UV_PROJECT_ENVIRONMENT=/tmp/jobpilot-venv \
  uv run pytest tests/checkpoint/test_sqlite_kill_restart.py -v -m checkpoint

# Postgres（需先启动 Postgres）
docker run -d --name pg-test -e POSTGRES_PASSWORD=pass -p 5432:5432 postgres:16
export POSTGRES_TEST_URL="postgresql://postgres:pass@localhost:5432/postgres"
UV_PROJECT_ENVIRONMENT=/tmp/jobpilot-venv \
  uv run pytest tests/checkpoint/test_postgres_kill_restart.py -v -m checkpoint
```

## 测试矩阵

| 场景 | SQLite | Postgres | 说明 |
|---|---|---|---|
| 5 轮后 kill | `test_kill_at_round_5_restart_continues` | `test_pg_kill_at_round_5_restart_continues` | 基本断点恢复 |
| 多次 kill | `test_kill_multiple_times` | `test_pg_kill_multiple_times` | 变态场景 |
| interrupt 期间 kill | `test_kill_during_interrupt_preserves_last_question` | `test_pg_kill_during_interrupt_preserves_last_question` | 问题不丢失 |
| 并发多 thread | `test_concurrent_threads_dont_interfere` | `test_pg_concurrent_threads_dont_interfere` | 隔离性 |

## 比对的严格字段

- `current_stage`：当前面试阶段
- `transcript`：完整对话记录（按 turn_id 排序）
- `performance_signals`：候选人表现评分
- `stage_round_count`：各阶段轮次计数
- `stage_history`：历史阶段轨迹
- `candidate_profile`：候选人档案（如已构建）
- `company` / `position`：会话身份

## 常见故障排查

| 症状 | 原因 | 解决 |
|---|---|---|
| `RuntimeError: Checkpointer not initialized` | FastAPI lifespan 未跑 `init_checkpointer()` | 检查 `main.py` lifespan hook |
| `StateInconsistency: Fields differ` | `_deep_equal` 没处理某个字段类型 | 检查 `state_comparator.py` |
| `TimeoutError: Agent not healthy` | 端口冲突或启动失败 | 检查进程日志，换端口 |
| `404 Thread not found` | 重启后 checkpointer 读不到状态 | 确认 SQLite 文件路径一致 |
| `403 Not allowed in production` | `APP_ENV=prod` | 测试进程传 `APP_ENV=dev` |
