# JobPilot Agent — Python AI 服务

JobPilot Agent 是 JobPilot 双栈架构中的 Python AI 推理层，基于 **FastAPI + LangGraph** 构建，负责 JD 路由分析、RAG 检索和模拟面试编排。Node.js Gateway 通过 HTTP 调用本服务，Python Agent 通过 `/internal/*` 回调 Node.js 访问飞书资源。

## 快速开始

### 前置要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)（包管理器）

### 安装依赖

```bash
cd python-agent
uv sync
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，至少填入 LLM_API_KEY
```

### 启动服务

```bash
uv run uvicorn jobpilot_agent.main:app --reload --port 8000
```

服务默认监听 `http://localhost:8000`。

## 目录结构

```
python-agent/
├── src/jobpilot_agent/
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # pydantic-settings 配置管理
│   ├── logging_setup.py     # structlog 结构化日志
│   ├── api/                 # HTTP 路由层
│   │   ├── schemas.py       # 全部 Pydantic v2 Model
│   │   ├── health.py        # GET /health
│   │   ├── jd_routing.py    # POST /api/v1/agent/jd-routing
│   │   └── interview.py     # POST/GET /api/v1/agent/interview/*
│   ├── graphs/              # LangGraph 图（当前为 stub）
│   ├── skills/              # Skill 基类与注册表
│   ├── retrieval/           # RAG 检索模块（当前为 stub）
│   ├── memory/              # LangGraph Checkpointer（当前为 stub）
│   ├── evaluation/          # 评估模块（待实现）
│   └── integrations/        # 外部集成（飞书代理、LLM 客户端）
└── tests/                   # pytest 测试套件
```

## API 文档

启动服务后访问：

- **Swagger UI**：http://localhost:8000/docs
- **ReDoc**：http://localhost:8000/redoc
- **OpenAPI JSON**：http://localhost:8000/openapi.json

## 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/v1/agent/jd-routing` | JD 路由分析（触发完整工作流） |
| POST | `/api/v1/agent/interview/start` | 开始模拟面试会话 |
| POST | `/api/v1/agent/interview/resume` | 继续面试会话 |
| GET | `/api/v1/agent/interview/{thread_id}/status` | 查询面试状态 |

## 测试

```bash
# 运行全部测试
uv run pytest

# 带覆盖率报告
uv run pytest --cov=jobpilot_agent --cov-report=term-missing

# 代码风格检查
uv run ruff check .

# 类型检查
uv run mypy src/
```

## 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_API_KEY` | 必填 | 火山方舟 API Key |
| `LLM_MODEL` | `doubao-pro-4k` | 主力模型 |
| `MILVUS_URI` | `http://localhost:19530` | Milvus 向量库地址 |
| `POSTGRES_URL` | `""` | PostgreSQL 连接串（LangGraph Checkpointer） |
| `NODEJS_CALLBACK_URL` | `http://localhost:3000/internal` | Node.js Gateway 内部回调 |
| `NODEJS_INTERNAL_SECRET` | `""` | 内部接口鉴权 Secret |

详见 `.env.example`。

## 技术栈

- **FastAPI** ≥ 0.110 — 异步 HTTP 框架
- **LangGraph** ≥ 0.2 — AI Agent 编排
- **Pydantic v2** — 数据校验
- **structlog** — 结构化日志
- **pymilvus** — 向量检索
- **uv** — 包管理
