# JobPilot for Feishu

JobPilot 是面向飞书场景的求职作战 Agent：**Node.js Gateway** 负责飞书接入、多维表格 / 文档 / 任务等副作用与业务编排；**Python Agent**（FastAPI）承载 LangGraph / RAG / LLM 推理。两端通过版本化的 **OpenAPI 契约**（`contracts/openapi.json`）同步类型，避免手写重复接口。

---

## 架构

### 双栈职责

| 层级 | 技术栈 | 职责 |
|------|--------|------|
| Gateway | Node.js + Express + TypeScript | 飞书 Webhook、事件解析与去重、JWT/Token 校验、多维表格写入、文档与任务、消息回复、简历上传解析、编排入口 |
| Agent | Python 3.11 + FastAPI + LangGraph（规划中） | JD 路由与分析、模拟面试会话等 AI 能力；可通过 HTTP 被 Gateway 调用 |
| 契约 | OpenAPI 3.1 → `openapi-typescript` | `contracts/openapi.json` 为单一真相源；`src/integrations/python-agent/generated.ts` 自动生成 |

### 组件关系（逻辑视图）

```text
┌─────────────────────────────────────────────────────────────────┐
│                         飞书开放平台                               │
└───────────────────────────────┬───────────────────────────────────┘
                                │ 事件订阅 Webhook
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Node.js Gateway（Express）                           │
│  ┌─────────────┐   ┌──────────────────┐   ┌─────────────────┐ │
│  │ Webhook /   │──▶│ Orchestrator      │──▶│ Feishu SDK 集成 │ │
│  │ 测试 API    │   │ (legacy / Python) │   │ bitable/doc/... │ │
│  └─────────────┘   └─────────┬─────────┘   └─────────────────┘ │
│                              │                                   │
│         USE_PYTHON_AGENT=true│ HTTP                              │
│                              ▼                                   │
│                    python-agent/client.ts                        │
│                              │                                   │
│  ┌───────────────────────────┴───────────────────────────────┐   │
│  │ POST /internal/feishu/*  （X-Internal-Secret，当前 stub）   │   │
│  └───────────────────────────────────────────────────────────┘   │
└───────────────────────────────┬───────────────────────────────────┘
                                │ 回调（预留）
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Python Agent（FastAPI）                              │
│  /health · /api/v1/agent/jd-routing · /api/v1/agent/interview/*   │
└─────────────────────────────────────────────────────────────────┘
```

### 仓库目录（精简）

```text
jobpilot-feishu/
├── src/                              # Node.js Gateway
│   ├── server.ts / app.ts
│   ├── config/                       # 环境变量（Zod / 必填校验）
│   ├── routes/                       # 路由（含 internal 回调 stub）
│   ├── controllers/                  # 飞书事件
│   ├── services/                     # 编排、JD 解析、记忆、简历等
│   ├── integrations/
│   │   ├── feishu/                   # 飞书 API 封装
│   │   └── python-agent/             # Python HTTP 客户端
│   │       ├── generated.ts          # ⚠️ openapi-typescript 生成，勿手改
│   │       ├── types.ts              # 从 generated 再导出，便于业务引用
│   │       └── client.ts
│   └── types/
├── contracts/
│   ├── openapi.json                  # ⚠️ 由 Python 导出脚本生成，勿手改
│   └── README.md
├── python-agent/
│   ├── src/jobpilot_agent/           # FastAPI、schemas、graphs（stub）等
│   ├── scripts/export_openapi.py     # 导出契约到 contracts/
│   └── README.md                     # Python 子项目说明
├── .github/workflows/contract-check.yml
├── Makefile
├── package.json
└── .env.example
```

---

## 运行流程

### 1. 飞书用户发 JD（生产主路径）

1. 用户在群内 @机器人发送 **文本 JD**。
2. `POST /webhook/feishu` 接收事件：`FeishuEventController` 校验 token、事件去重、**先返回 200** 再异步处理。
3. 文本经 `validateJDInput` 校验后，`orchestratorService.execute(jdText, { userId: openId })` 执行主流程。
4. **编排**（见下节）产出 `OrchestratorResult`，组装为飞书消息回复；失败则回复错误提示。
5. 文件类消息走简历 PDF 分支，调用 `resumeIngestionService`，与 JD 流程独立。

### 2. 编排器：`USE_PYTHON_AGENT`

- `USE_PYTHON_AGENT=false`（默认）：走 `orchestrator.legacy.ts`，在 Node 内用 LLM + 飞书写入等完整逻辑。
- `USE_PYTHON_AGENT=true`：优先 `pythonAgentClient.postJdRouting`；若超时或错误则 **降级** 到 legacy，保证可用性。
- Gateway 将 Python 返回的 `classification` / `results` **映射**为现有 `OrchestratorResult`（飞书副作用占位由 Node 侧策略决定）。

### 3. 本地调试（不经过飞书）

| 用途 | 命令 / 地址 |
|------|----------------|
| 启动 Gateway | `npm run dev` → 默认 `http://localhost:3000`（`PORT` 可改） |
| 健康检查（含探测 Python） | `GET http://localhost:3000/health` |
| 直接跑 JD 分析 | `POST http://localhost:3000/api/test/analyze`，Body：`{"jd_text":"..."}` |
| 上传简历 PDF（HTTP） | `POST http://localhost:3000/api/test/resume`（multipart，需 `user_id`） |

### 4. Python Agent 单独启动

```bash
cd python-agent && uv sync
cp .env.example .env   # 配置 LLM_API_KEY 等
```

```bash
# 默认文档示例为 8000；若本机 8000 被占用（如 Apache），可改用 8001
make dev-py
# 并将 Gateway 的 PYTHON_AGENT_URL 设为对应地址，例如 http://127.0.0.1:8001
```

- Swagger：`http://127.0.0.1:<port>/docs`
- 根路径 `/` 未定义路由时返回 404 属正常，请以 `/health`、`/docs` 为准。

### 5. 内部回调（预留）

Python 将来可通过 `NODEJS_CALLBACK_URL` 调用 Gateway 的 `POST /internal/feishu/docs/read`、`bitable/query`、`files/upload`，请求头带 `X-Internal-Secret`（与 Node 侧 `INTERNAL_SECRET` 对齐）。当前为 **stub**，实现会在后续迭代替换。

---

## API 契约与类型同步

修改 **Python** 侧 `schemas` 后必须同步契约与 TS 类型，禁止手工编辑 `contracts/openapi.json` 与 `generated.ts`。

```bash
make contracts
# 等价：cd python-agent && uv run python scripts/export_openapi.py
#      npm run gen:types
```

完成同步后，`openapi.json` 与 `generated.ts` 须与 Python Schema 及 Gateway 调用代码保持一致；二者均为自动生成，勿手工修改。

详见 [`contracts/README.md`](contracts/README.md)。

---

## Makefile 常用目标

在无 `make` 的 Windows 环境可手动执行注释中的等价命令。

| 目标 | 说明 |
|------|------|
| `make contracts` | 导出 OpenAPI + 生成 `generated.ts` |
| `make dev-node` / `make dev-py` | 启动 Gateway / Python Agent |
| `make test-all` | `pytest` + `vitest` |
| `make build-node` | `npm run build` |
| `make lint-node` / `make lint-py` | ESLint / Ruff |

`make help` 列出全部目标。

---

## 测试与质量

```bash
make test-all           # 推荐
npm test                # Vitest（Gateway）
cd python-agent && uv run pytest
npm run lint && npm run build
```

---

## 环境变量（概要）

| 区域 | 文件 | 说明 |
|------|------|------|
| Gateway | [`.env.example`](.env.example) | 飞书应用、多维表格、LLM、`USE_PYTHON_AGENT`、`PYTHON_AGENT_URL`、`INTERNAL_SECRET` 等 |
| Python Agent | [`python-agent/.env.example`](python-agent/.env.example) | `LLM_API_KEY`、`POSTGRES_URL`、`NODEJS_CALLBACK_URL`、`NODEJS_INTERNAL_SECRET` 等 |

**注意**：Gateway 默认 `PYTHON_AGENT_URL=http://localhost:8000`，若本地 Agent 跑在 `8001`，请修改 `.env` 与两边约定一致。

---

## 延伸阅读

- Python 子项目细节：[`python-agent/README.md`](python-agent/README.md)
- 契约目录说明：[`contracts/README.md`](contracts/README.md)
