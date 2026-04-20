# Orchestration Layer

主图（JD 路由）与面试子图之间的桥梁层。

## 为什么要有这层？

两张 LangGraph 的 State schema 完全不同，且生命周期也不同（主图一次性，子图跨会话）。
直接用 `add_node(subgraph)` 嵌套会导致 interrupt 语义混乱和 Checkpointer 复杂度暴增。

**方案 C**（本层实现）：主图跑完 → API 层写 Redis → 用户点按钮 → 面试 API 读 Redis → 启动子图。
两图互不感知，解耦清晰。

## Session Context Store

文件：`session_context.py`

| 方法 | 说明 |
|---|---|
| `save(chat_id, context)` | 写入 `session_context:{chat_id}`，TTL 24 小时 |
| `load(chat_id)` | 读取，不存在则返回 `None` |
| `clear(chat_id)` | 删除 key |
| `ping()` | 健康检查，返回 `bool` |

**为什么选 Redis 而非 Postgres**：TTL 逻辑在 Redis 更自然（`SETEX`），24 小时后自动过期无需 cron 清理。Postgres 需要额外的过期字段 + 定时任务。

**Key 命名**：`session_context:{feishu_chat_id}`。`feishu_chat_id` 来自 `JDRoutingRequest.user_context.feishu_chat_id`，若为空则 fallback 到 `user_id`。

## 使用约束

- Redis 调用**只在 API 层**发生（`jd_routing.py` 写，`interview.py` 读）
- Graph 节点保持纯净，不直接调 Redis
- `init_session_node` 通过 `state.metadata.source_session_context` 获取主图上下文（API 层通过 initial_state 传入）
- Redis 不可达时降级为 `None`（不崩溃），面试 API 改为要求显式传入 company/position
