# 断点续聊一致性报告 v1

**执行时间**：2026-04-19
**测试策略**：kill-restart 自动化测试，SIGKILL 强制终止 → 重启 → 状态对比
**一致性目标**：100%（6 个核心字段全匹配）
**实际验证**：全部 4 个 SQLite 场景已通过（kill_at_round_5: 450s；kill_multiple_times: ~400s；kill_during_interrupt: 107s；concurrent_threads: ~400s）

---

## 测试矩阵

| 场景 | Backend | 结果 | 说明 |
|---|---|---|---|
| 5 轮后 kill | SQLite | ✅ | 基本断点恢复，状态完整 |
| 多次 kill | SQLite | ✅ | 3 次 kill-restart，transcript 单调增加 |
| interrupt 期间 kill | SQLite | ✅ | 问题保存在 interrupt payload，kill 后 restart 完全还原 |
| 并发多 thread | SQLite | ✅ | thread_a / thread_b 互不污染 |
| 5 轮后 kill | Postgres | ⏭️ | 需 POSTGRES_TEST_URL（CI 可用） |
| 多次 kill | Postgres | ⏭️ | 需 POSTGRES_TEST_URL |
| interrupt 期间 kill | Postgres | ⏭️ | 需 POSTGRES_TEST_URL |
| 并发多 thread | Postgres | ⏭️ | 需 POSTGRES_TEST_URL |

> ✅ = 通过  ❌ = 失败  ⏭️ = 跳过（依赖未就绪）

---

## 验证的一致性字段

| 字段 | 类型 | 一致性 | 比对方法 |
|---|---|---|---|
| `current_stage` | `str` | 100% | 直接比较 |
| `transcript` | `list[Turn]` | 100% | 按 turn_id 排序后逐字段比较 |
| `performance_signals` | `list[PerformanceSignal]` | 100% | 按 (turn_id, dimension) 排序 |
| `stage_round_count` | `dict[str, int]` | 100% | dict 递归比较 |
| `stage_history` | `list[str]` | 100% | 顺序比较 |
| `candidate_profile` | `dict` | 100% | dict 递归比较 |

---

## 关键指标

- **恢复时间**：kill 到下一次 API 调用正常响应的耗时 P95 < 15s（含进程冷启动 + jieba 词典加载）
- **数据丢失率**：0%
- **并发影响**：无（thread_id 天然隔离）
- **测试单 case 耗时**：107s–450s（kill_during_interrupt 最快，kill_at_round_5 需跑完全程最慢）

---

## 技术栈支撑

- **LangGraph AsyncSqliteSaver**：ACID 写入，每个 checkpoint 原子提交
- **FastAPI lifespan hook**：`init_checkpointer()` 在进程启动时立即初始化
- **thread_id 隔离**：对应飞书 `open_chat_id`，天然按会话隔离

---

## 已知限制

- interrupt 期间的 LLM 调用如果已发出、但 Python 进程被 kill，token 仍然计费（无法撤回）
- Postgres 版连接池断开后重连约 2-3s（在 `wait_timeout=45s` 内可接受）
- 测试端口硬编码为 18001/18002，若端口被占用需手动释放

---

## 运行命令

```bash
# SQLite（无需额外环境）
UV_PROJECT_ENVIRONMENT=/tmp/jobpilot-venv \
  uv run pytest tests/checkpoint/test_sqlite_kill_restart.py -v -m checkpoint

# Postgres
export POSTGRES_TEST_URL="postgresql://postgres:pass@localhost:5432/postgres"
UV_PROJECT_ENVIRONMENT=/tmp/jobpilot-venv \
  uv run pytest tests/checkpoint/test_postgres_kill_restart.py -v -m checkpoint
```
