<div align="center">

# JobPilot Agent

**基于 LangGraph 的求职全流程智能体系统**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Node.js 18+](https://img.shields.io/badge/node-18+-green.svg)](https://nodejs.org/)
[![Docker](https://img.shields.io/badge/docker-compose-blue.svg)](https://docs.docker.com/compose/)

[📊 场景 A 评估报告](python-agent/evaluation/reports/scenario_a_v1.md) · [🎤 Replay 评估](python-agent/evaluation/reports/replay_evaluation_v1.md) · [🏗️ 架构设计](ARCHITECTURE.md) · [📦 数据集说明](DATASETS.md) · [📏 评估方法](EVALUATION.md)

</div>

---

## 🎯 一句话介绍

> 运行在飞书中、**以 JD 为入口、以复盘报告为出口**的端到端求职 Agent。
> 用 RAG + LangGraph 把「岗位分析 → 简历建议 → 模拟面试 → 复盘反馈」全链路跑通。

## 💡 为什么做这个

传统 LLM 求职工具三大缺陷:

- **无记忆**:每次冷启动,不知道你上次投过什么
- **无结构**:多轮对话管不住状态,三轮就崩
- **无依据**:答案全凭 LLM 编,幻觉严重

我们通过 RAG 混合检索 + LangGraph 状态机 + 三层评估体系 **逐一解决**这三个痛点。

## 📊 项目亮点(硬数据)

全部数字来自 `python-agent/evaluation/reports/` 原始评估,任何一条可回溯到 JSONL 原始记录:

| 能力 | 指标 | 目标 | 实测 | 备注 |
|---|---|---|---|---|
| **断点续聊一致性** | 状态恢复率 | 100% | **100%**(4/4 SQLite) | 6 字段全绿 |
| **Skill 路由节流** | Over-invocation Rate | < 10% | **0.6%** | Baseline 为 100%(强制全调) |
| **Skill 路由成本** | Token 降幅 vs Baseline | ≥ 30% | **28.1%** | 差 2 pp,接近目标 |
| **Interview Replay Rank@3** | 下一问预测命中 | > 60% | **93.3%** | 30 对 history→next |
| **Interview Replay Rank@5** | 下一问预测命中 | > 85% | **93.3%** | 同上 |
| **JD 分类** | job_type Macro F1 | > 85% | **64.8%** | sub_type 标注一致性是短板 |
| **Stage 预测** | Accuracy | > 85% | **72.3%** | project_deep_dive / scenario 易混 |
| **端到端 P95 延迟** | 一次 JD 路由总耗时 | < 8s | **76.4s** | W6 P6.1 优化中(`embedding cache + prompt 裁剪`) |

> 评估集规模:500 条 JD 路由(全量)、300 条阶段推进样本、30 对 Replay pair、4 个断点续聊自动化场景。
> 详细口径:[EVALUATION.md](EVALUATION.md)

### 正在攻坚

`final_synthesis` 节点的 LLM 合成占 P95 总延迟 65%(35s mean → 49s P95)。W6 P6.1 已落地 Embedding LRU 缓存 + prompt 压缩 ≥50%,待真机跑一遍给出回归对比。

## 🏗️ 技术架构

```text
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   飞书 IM    │ ───→ │ Node.js BFF  │ ───→ │ Python Agent │
│   多维表格   │      │   (网关层)   │      │ (LangGraph)  │
│   文档       │ ←─── │              │ ←─── │   (RAG)      │
└──────────────┘      └──────────────┘      └──────────────┘
                                                    │
                                    ┌───────────────┼───────────────┐
                                    ▼               ▼               ▼
                                Milvus          Postgres           Redis
                                (向量 KB)      (Checkpointer)   (SessionCtx)
```

**双栈架构**:Node.js 负责飞书集成与副作用(bitable/doc/task),Python 负责 AI 推理(LangGraph/RAG/Skill)。
分工理由详见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 📦 单机部署指南(生产模式)

> 本节覆盖**无 Docker** 的单机生产部署:直接在宿主机安装依赖、以生产模式启动两个服务、对接飞书。
> 开发模式请看本文件末尾的 [🔧 开发常用](#-开发常用)。

### 0. 系统要求

| 组件 | 版本 | 用途 |
|---|---|---|
| **操作系统** | Linux(Ubuntu 22.04+ / CentOS 8+ / Debian 12+)或 macOS 12+ | 生产宿主机 |
| **Python** | ≥ 3.11,< 3.13 | Python Agent 运行时 |
| **Node.js** | ≥ 18(建议 20 LTS) | Gateway 运行时 |
| **Redis** | ≥ 7.0 | SessionContext 桥(主图→面试子图) |
| **PostgreSQL**(可选) | ≥ 15 | LangGraph Checkpointer;不装可回退 SQLite |
| **Milvus**(可选) | ≥ 2.4 | 向量库;不装可回退 Chroma 本地文件 |
| **uv** | ≥ 0.4 | Python 包管理(替代 pip) |
| **GNU Make** | 任意 | 命令编排(非必须) |
| **公网反代**(可选) | Nginx / Caddy | 把 3000 端口暴露给飞书服务器 |

**硬件建议**:4 核 CPU / 8 GB RAM / 30 GB SSD。使用 Chroma + SQLite 的最简形态可压到 2 核 / 4 GB。

---

### 1. 安装运行时依赖

**Python 3.11 + uv**(Ubuntu/Debian 示例):

```bash
# Python 3.11(如发行版不带)
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3.11-dev

# uv(官方一键脚本)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv --version   # 校验
```

**Node.js 20**(nvm 路线,生产稳定):

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc
nvm install 20 && nvm use 20
node -v   # 应输出 v20.x
```

**Redis 7**(必装):

```bash
sudo apt install -y redis-server
sudo systemctl enable --now redis-server
redis-cli ping   # 期望输出 PONG
```

**PostgreSQL 15**(推荐;也可跳过改用 SQLite):

```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
sudo -u postgres psql <<'SQL'
CREATE USER jobpilot WITH PASSWORD 'strong_password_here';
CREATE DATABASE jobpilot OWNER jobpilot;
GRANT ALL PRIVILEGES ON DATABASE jobpilot TO jobpilot;
SQL
```

**Milvus 2.4**(可选;生产推荐用官方二进制,见 [milvus.io](https://milvus.io/docs/install_standalone-docker.md) 非 Docker 方案。**若跳过此步**,配置中开启 `RETRIEVAL_FALLBACK_TO_CHROMA=true`,系统自动使用本地 Chroma,完全可用,仅检索性能略低)。

---

### 2. 拉取代码并安装项目依赖

```bash
git clone <repo-url> /opt/jobpilot-feishu
cd /opt/jobpilot-feishu

# Python Agent
cd python-agent
uv sync --extra eval          # 生产依赖 + 评估依赖
# 如用 PostgreSQL Checkpointer,额外:
#   uv pip install "psycopg[binary]>=3.2"
cd ..

# Node.js Gateway
npm ci                        # 严格按 package-lock.json 装
npm run build                 # 编译 TypeScript → dist/
```

---

### 3. 配置环境变量(生产值)

**Gateway** — 复制并填写 `/opt/jobpilot-feishu/.env`

```bash
cp .env.example .env
```

关键项(生产必填):

```ini
PORT=3000
NODE_ENV=production                         # 必须
LOG_LEVEL=info

# 飞书凭证(后面第 5 步获取)
FEISHU_APP_ID=cli_xxxxxxxx
FEISHU_APP_SECRET=xxxxxxxx
FEISHU_VERIFICATION_TOKEN=xxxxxxxx
FEISHU_ENCRYPT_KEY=                         # 可选,若启用加密则填
FEISHU_BITABLE_APP_TOKEN=bascnXXXXX
FEISHU_BITABLE_TABLE_ID=tblXXXXX

# LLM(DeepSeek 推荐)
LLM_API_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxxxx
LLM_MODEL=deepseek-chat

# 双栈桥接
USE_PYTHON_AGENT=true
PYTHON_AGENT_URL=http://127.0.0.1:8001      # 与下面 Python APP_PORT 对齐
PYTHON_AGENT_TIMEOUT_MS=60000

# Python→Node 回调鉴权(随机 32 字节)
INTERNAL_SECRET=$(openssl rand -hex 32)     # 复制生成值到此处
```

**Python Agent** — `/opt/jobpilot-feishu/python-agent/.env`

```bash
cd python-agent && cp .env.example .env
```

```ini
APP_ENV=prod
APP_PORT=8001
LOG_LEVEL=INFO

LLM_API_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxxxx
LLM_MODEL=deepseek-chat
LLM_MODEL_LITE=deepseek-chat

# 向量库:装了 Milvus 就指向它;没装就设 RETRIEVAL_FALLBACK_TO_CHROMA=true
MILVUS_URI=http://localhost:19530
RETRIEVAL_FALLBACK_TO_CHROMA=true
CHROMA_PERSIST_DIR=/opt/jobpilot-feishu/python-agent/data/chroma

# Checkpointer 后端(二选一)
CHECKPOINTER_BACKEND=postgres                                           # 生产推荐
POSTGRES_URL=postgresql://jobpilot:strong_password_here@localhost:5432/jobpilot
# 或降级 SQLite:
# CHECKPOINTER_BACKEND=sqlite
# SQLITE_CHECKPOINT_PATH=/opt/jobpilot-feishu/python-agent/data/checkpoints.db

REDIS_URL=redis://localhost:6379

# Node 回调(两端 Secret 必须一致)
NODEJS_CALLBACK_URL=http://127.0.0.1:3000/internal
NODEJS_INTERNAL_SECRET=<与 Gateway INTERNAL_SECRET 完全相同>

EMBEDDING_PROVIDER=local
EMBEDDING_MODEL_NAME=BAAI/bge-m3
EMBEDDING_DIMENSION=1024
EMBEDDING_CACHE_ENABLED=true
EMBEDDING_CACHE_SIZE=10000
```

> ⚠️ `INTERNAL_SECRET`(Node 侧)与 `NODEJS_INTERNAL_SECRET`(Python 侧)**必须完全相同**,否则 Python→Node 回调一律 401。

---

### 4. 初始化数据与索引

```bash
cd /opt/jobpilot-feishu/python-agent

# 构建 BM25 索引(JD 库 + 面经库)
uv run python -m kb_builder.build_bm25 \
  --input ../knowledge-base/data/labeled/jd_labeled.jsonl \
  --output ./data/bm25_indexes/jd.pkl
uv run python -m kb_builder.build_bm25 \
  --input ../knowledge-base/data/clean/interview_structured_filtered.jsonl \
  --output ./data/bm25_indexes/interview.pkl

# 向量入库(Milvus 或 Chroma 自动走配置)
uv run python ../knowledge-base/src/kb_builder/ingest_jd.py
uv run python ../knowledge-base/src/kb_builder/ingest_interview.py

# 预拉 BGE-M3 模型到本地(首次很慢,约 2 GB)
uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"
```

---

### 5. 飞书应用对接

#### 5.1 创建应用并取凭证

1. 登录 [飞书开放平台](https://open.feishu.cn) → **创建企业自建应用**。
2. **凭证与基础信息** → 复制 `App ID` / `App Secret` → 填入 Gateway `.env` 的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`。
3. **事件与回调 → 加密策略** → 复制 `Verification Token` 填 `FEISHU_VERIFICATION_TOKEN`;若启用加密,复制 `Encrypt Key` 填 `FEISHU_ENCRYPT_KEY`。

#### 5.2 申请权限

在 **权限管理** 搜索并开启以下 scope(最小集):

| 分类 | 权限 |
|---|---|
| 消息 | `im:message`、`im:message.group_at_msg`、`im:message.p2p_msg`、`im:message:send_as_bot` |
| 卡片 | `im:resource`(回复交互卡片) |
| 多维表格 | `bitable:app`(读/写多维表格) |
| 云文档 | `docx:document`、`drive:drive`(读写复盘报告) |
| 用户 | `contact:user.id:readonly`(把 open_id 关联到用户档案) |

#### 5.3 配置事件订阅

1. **事件与回调 → 事件配置 → 将应用发布到企业内** 前先设置订阅方式:
   - **请求地址**:`https://<你的公网域名>/feishu/events`(Gateway 的 webhook 端点)
   - 未提供公网 IP 时,可用 Cloudflare Tunnel 或 frp 做反向代理(见 5.4)。
2. **订阅事件**(点 `+ 添加事件`):
   - `im.message.receive_v1` — 接收单聊/群消息
   - `card.action.trigger` — 面试邀请卡片按钮回调
3. 保存后飞书会向你的 URL 发 challenge,Gateway 必须已启动并能回包。

#### 5.4 公网暴露(二选一)

**Nginx 反代**(推荐,有自有域名):

```nginx
server {
  listen 443 ssl http2;
  server_name bot.yourdomain.com;
  ssl_certificate     /etc/letsencrypt/live/bot.yourdomain.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/bot.yourdomain.com/privkey.pem;

  location /feishu/ {
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 300s;   # 长请求留足时间
  }
}
```

**Cloudflare Tunnel**(零公网 IP):

```bash
cloudflared tunnel login
cloudflared tunnel create jobpilot
cloudflared tunnel route dns jobpilot bot.yourdomain.com
cloudflared tunnel run --url http://127.0.0.1:3000 jobpilot
```

#### 5.5 发布应用

**应用发布 → 创建版本 → 提交审核 → 企业内可用**。审核通过后,群聊 @bot 或 DM 才能触发消息事件。

---

### 6. 以生产模式启动

使用 `systemd` 做进程管理(生产唯一推荐方式)。

**Python Agent service** — `/etc/systemd/system/jobpilot-agent.service`

```ini
[Unit]
Description=JobPilot Python Agent
After=network.target redis-server.service postgresql.service

[Service]
Type=simple
User=jobpilot
WorkingDirectory=/opt/jobpilot-feishu/python-agent
EnvironmentFile=/opt/jobpilot-feishu/python-agent/.env
ExecStart=/home/jobpilot/.local/bin/uv run uvicorn jobpilot_agent.main:app \
          --host 127.0.0.1 --port 8001 --workers 2 --log-level info
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Node.js Gateway service** — `/etc/systemd/system/jobpilot-gateway.service`

```ini
[Unit]
Description=JobPilot Node Gateway
After=network.target jobpilot-agent.service

[Service]
Type=simple
User=jobpilot
WorkingDirectory=/opt/jobpilot-feishu
EnvironmentFile=/opt/jobpilot-feishu/.env
Environment=NODE_ENV=production
ExecStart=/home/jobpilot/.nvm/versions/node/v20.18.0/bin/node dist/server.js
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

> 注意 `ExecStart` 里的 `node` 和 `uv` 必须是绝对路径(systemd 不继承登录 shell 的 PATH)。用 `which node` / `which uv` 查实际路径后替换。

**启用并启动**:

```bash
sudo useradd -m -s /bin/bash jobpilot
sudo chown -R jobpilot:jobpilot /opt/jobpilot-feishu

sudo systemctl daemon-reload
sudo systemctl enable --now jobpilot-agent jobpilot-gateway

# 查看状态
sudo systemctl status jobpilot-agent
sudo systemctl status jobpilot-gateway

# 日志
sudo journalctl -u jobpilot-agent -f
sudo journalctl -u jobpilot-gateway -f
```

---

### 7. 部署校验

```bash
# Python Agent 健康
curl http://127.0.0.1:8001/health
# 期望:{"status":"ok", ...}

# Gateway 健康(会探测 Python 可达性)
curl http://127.0.0.1:3000/health
# 期望:{"status":"ok","python_agent":{"reachable":true,...}}

# 公网回环(飞书会这样调你)
curl https://bot.yourdomain.com/feishu/events \
  -H 'Content-Type: application/json' \
  -d '{"type":"url_verification","challenge":"test"}'
# 期望:{"challenge":"test"}

# 端到端联调:在飞书群 @bot 粘贴一段 JD 文本,观察:
#   1) bot 回复 JD 分析卡片
#   2) 卡片底部出现"开始模拟面试"按钮
#   3) 点击按钮进入面试多轮对话
```

---

### 8. 运维常识

| 场景 | 操作 |
|---|---|
| 改代码 / 升级版本 | `git pull && npm ci && npm run build && cd python-agent && uv sync && cd ..`,再 `sudo systemctl restart jobpilot-agent jobpilot-gateway` |
| 改 `.env` | `sudo systemctl restart <服务>`(EnvironmentFile 在 systemd 下不会自动 reload) |
| 改 Pydantic schema | 必须 `make contracts` → 提交 `openapi.json` + `generated.ts` → 重新 `npm run build` → 重启 Gateway |
| 磁盘清理 | BGE-M3 权重约 2 GB 在 `~/.cache/huggingface/`;Chroma/SQLite 持久化在 `python-agent/data/` |
| 日志轮转 | systemd 默认走 journald,`sudo journalctl --vacuum-size=500M` 控制体积 |

### 9. 常见故障速查

| 症状 | 排查 |
|---|---|
| Gateway 启动报 `缺少必要环境变量` | `.env` 漏填必填项(`FEISHU_APP_ID` 等) |
| `/health` 的 `python_agent.reachable=false` | Python 未起 / `PYTHON_AGENT_URL` 端口对不上(常见坑:Python 跑 8001,Gateway 默认 8000) |
| 飞书事件 URL 验证失败 | `FEISHU_VERIFICATION_TOKEN` 不匹配;或公网地址未到达 3000 端口 |
| Python→Node 回调一律 401 | `INTERNAL_SECRET` 两侧不一致 |
| 面试子图重启后丢状态 | 用了 SQLite 但切换了 `SQLITE_CHECKPOINT_PATH`;或未切到 Postgres Checkpointer |
| 首次调用极慢(30s+) | BGE-M3 首次下载 2 GB 权重;按步骤 4 预拉即可

## 📁 目录结构

```text
jobpilot-feishu/
├── README.md                    # 你在看的文件
├── ARCHITECTURE.md              # 技术架构(为什么双栈 / LangGraph 4 能力 / ADR)
├── DATASETS.md                  # 数据集说明 + 合法性
├── EVALUATION.md                # 评估方法论
├── CHANGELOG.md                 # 6 周进度日志
├── CLAUDE.md                    # Claude Code 工作指引
├── Makefile                     # 常用命令
├── docker-compose.yml
├── .env.example
│
├── src/                         # Node.js Gateway(飞书侧)
│   ├── controllers/             # Feishu webhook
│   ├── services/                # orchestrator / intent / chat-state
│   ├── integrations/
│   │   ├── feishu/              # 飞书 SDK 封装
│   │   └── python-agent/        # HTTP client + 生成的 TS 类型
│   └── routes/internal.routes.ts  # Python → Node 回调
│
├── python-agent/                # Python AI Agent
│   ├── src/jobpilot_agent/
│   │   ├── api/                 # FastAPI 路由 + Pydantic schemas
│   │   ├── graphs/              # 主图 + 面试子图(LangGraph)
│   │   ├── skills/              # 6 个 Skill
│   │   ├── retrieval/           # RAG:BM25 + Milvus/Chroma + RRF
│   │   ├── orchestration/       # SessionContext(Redis)
│   │   └── evaluation/          # 三层评估框架
│   ├── evaluation/
│   │   ├── reports/             # 评估报告(scenario_a / replay / stage / checkpoint)
│   │   └── runs/                # 原始 JSONL 评估数据
│   ├── tests/
│   └── scripts/
│
├── knowledge-base/              # 数据集 + 入库工具
│   ├── data/
│   │   ├── labeled/jd_labeled.jsonl                (500 条)
│   │   └── clean/interview_structured_filtered.jsonl  (643 条)
│   └── src/kb_builder/
│
├── contracts/                   # 两端 API 契约(openapi-typescript 生成)
│   └── openapi.json
│
└── docs/
    ├── e2e_flow.md              # JD → 面试 时序图
    ├── demo_script.md           # 答辩演示脚本
    └── performance/             # P6.1 profile 产物目录
```

## 📚 核心文档导航

| 你想了解... | 读这份 |
|---|---|
| 项目背景与设计思路 | [AI项目报告.md](AI项目报告.md)(如在仓库根部) |
| 双栈架构为什么这么设计 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 数据集怎么来的、合规吗 | [DATASETS.md](DATASETS.md) |
| 评估方法详细步骤 | [EVALUATION.md](EVALUATION.md) |
| 场景 A 全量评估原始报告 | [scenario_a_v1.md](python-agent/evaluation/reports/scenario_a_v1.md) |
| Interview Replay 原理与结果 | [replay_evaluation_v1.md](python-agent/evaluation/reports/replay_evaluation_v1.md) |
| 断点续聊自动化验证 | [checkpoint_consistency_v1.md](python-agent/evaluation/reports/checkpoint_consistency_v1.md) |
| 6 周是怎么推进的 | [CHANGELOG.md](CHANGELOG.md) |
| JD → 面试端到端时序 | [docs/e2e_flow.md](docs/e2e_flow.md) |
| 答辩演示讲稿 | [docs/demo_script.md](docs/demo_script.md) |

## 🏆 项目核心贡献

1. **四件套技术落地**:RAG 混合检索(BM25 + Milvus + RRF + BGE rerank)+ LangGraph(分支/循环/中断/持久化)+ RAGAS 评估 + Scenario A/B 自建评估 —— 一个都不少、每一个都有可回溯数据
2. **两份自建评估集**:500 条 JD 路由 + 643 条结构化面经(合规声明见 DATASETS.md)
3. **三层评估金字塔**:检索层 RAGAS + 编排层 F1/Latency/Cost + 对话层 Replay/Stage/Checkpoint
4. **创新评估方法**:Interview Replay —— 把主观的"面试逼真度"转成客观的"下一问预测",Rank@3 达到 93.3%
5. **端到端闭环**:飞书粘贴 JD → 面试邀请卡片 → 多轮追问 → 复盘报告,全链路真机可跑(see `docs/e2e_flow.md`)
6. **工程化严肃**:双栈 OpenAPI 契约强制同步 + CI contract-check + ack-first webhook + Checkpointer SIGKILL 一致性 100%

## 🔧 开发常用

```bash
# 契约同步(改 Python schema 后必跑)
make contracts

# 测试
make test-all                # pytest + vitest
npm test                     # vitest only
cd python-agent && uv run pytest          # pytest only
cd python-agent && uv run pytest -m integration    # 需要 Milvus/Postgres

# 构建与检查
make build-node              # tsc
make lint-node / make lint-py
cd python-agent && uv run mypy src/
```

## 🔐 License & Disclaimer

- 代码:MIT License
- 数据集:仅用于非商业研究评估,禁止公开分发(详见 [DATASETS.md](DATASETS.md))
- 本项目系飞书校园挑战赛参赛作品

## 🙋 作者

本项目作者信息见报名表(`docs/registration_form.md`)。
