# 🚀 JobPilot for Feishu / 求职作战官

> 一个运行在飞书中的垂直场景办公 Agent，帮助求职者从「收到 JD」到「完成面试准备」的全流程提效。

## ✨ 项目亮点

- **聊天即触发**：在飞书对话中发送一段 JD，即可自动启动完整分析流程
- **LLM 编排引擎**：多步骤 Prompt 分离设计，结构化解析 → 总结 → 简历建议 → 面试题
- **飞书生态打通**：多维表格记录、任务创建、文档生成一步到位
- **轻量求职记忆（可选）**：基于飞书多维表格的画像 / 岗位过程 / 周期摘要，让输出更连续；未配置或失败时自动降级
- **多维表格自动补列**：主业务台账表与三张记忆表在写入/检索前对齐列结构，缺列则调用飞书 API 创建，避免因缺列整链失败
- **优雅降级**：任一外部调用失败不影响主流程，用户始终获得最大可用结果
- **比赛就绪**：清晰的工程结构、完整类型定义、模块化设计，适合答辩展示

## 📋 功能概览

| 功能 | 描述 |
|------|------|
| JD 结构化解析 | 提取公司、岗位、职责、要求、技能等字段 |
| 岗位要求总结 | 100~200 字精炼总结；可结合用户记忆做轻微个性化 |
| 简历修改建议 | 5~8 条可执行建议；可结合历史缺口与画像薄弱项 |
| 面试题预测 | 3 道高概率面试题 + 出题意图 + 回答要点；可结合记忆约束表述 |
| 主业务多维表格 | 每次写入前按 `BITABLE_FIELD_MAP` 自动补列后新增一行求职台账 |
| 轻量记忆（三张表） | `user_profile` / `job_records` / `memory_summary`；读写在检索/写入前自动补列 |
| 跟进任务创建 | 自动创建带截止时间的飞书任务 |
| 面试准备文档 | 自动生成结构化文档并返回链接 |
| 结果消息回传 | 将全部结果以清晰格式推送到聊天 |

## 🔔 功能触发说明（答辩 / Demo 必读）

以下说明**谁在什么条件下触发**，便于对照代码与现场演示。

### 1. 飞书聊天里分析 JD（主流程）

| 步骤 | 触发条件 | 行为 |
|------|----------|------|
| 收到消息 | 飞书事件 `im.message.receive_v1`，且消息为文本、内容通过长度校验 | `FeishuEventController` 异步处理 |
| 执行编排 | 上述校验通过后 | `orchestratorService.execute(jdText, { userId })`，`userId` 为发送者 `open_id`（有则传，无则等价旧版） |
| 拉取记忆 | `userId` 非空 **且** `.env` 中三张记忆表 ID 均已配置 | `memoryService.getMemoryContextForJobAnalysis`；否则不读记忆 |
| LLM 并行 | JD 解析完成后 | 岗位总结、简历建议、面试题并行调用；若存在记忆则注入 `LightMemoryPromptContext` |
| 写主业务表 | 编排阶段 3，与其它飞书写入并行 | `feishuBitableService.addRecord` → **写入前**按 `BITABLE_MAIN_SCHEMA` 自动补列 |
| 写记忆表 | 同上阶段 3，且 `userId` 非空 **且** 记忆表已配置 | `persistJobMemory` → `refreshAfterJobProcessing`（岗位记录 + rolling 摘要 + 活跃时间）；失败仅打日志 |
| 回复用户 | 编排完成后 | 拼装文本回复（含多维表格/任务/文档状态） |

### 2. 主业务多维表格「自动补列」

| 触发点 | 条件 | 行为 |
|--------|------|------|
| `addRecord` / `addRecords` | 每次向 `FEISHU_BITABLE_APP_TOKEN` + `FEISHU_BITABLE_TABLE_ID` 写入 | 先 `list` 字段，再对 `BITABLE_FIELD_MAP` 中缺失的中文列名调用「新增字段」API；`创建时间` 列为日期类型，其余默认文本 |
| 失败策略 | 无建列权限或 API 报错 | 打 `warn`，不抛错到业务外层；后续写入仍可能失败，由原有 `writeBitable` try/catch 标记失败 |

### 3. 记忆三张表「自动补列」

| 触发点 | 条件 | 行为 |
|--------|------|------|
| 记忆表检索 / 写入 | 任意使用 `searchRecordsInTable` / `createRecordInTable` / `updateRecordInTable` 且传入对应 `MEMORY_*_SCHEMA` | 写入/检索前对齐该表全部约定列（见 `constants/index.ts`） |
| 标签类数组 | 写入记忆表 | `encodeMemoryFields(..., { joinArrayValues: true })` 将 `string[]` 拼为「、」文本，兼容自动创建的文本列；读出时 `readStringArray` 同时兼容多选控件与纯文本 |

### 4. 本地 HTTP 调试（不经飞书事件）

| 触发 | 条件 | 行为 |
|------|------|------|
| `POST /api/test/analyze` | 请求体带 `jd_text` | 调用编排器；**不传** `userId`，故不会走记忆读写（与飞书链路区分） |

---

## 🏗️ 项目结构

```
jobpilot-feishu/
├── package.json
├── tsconfig.json
├── .env.example            # 环境变量模板
├── .gitignore
├── README.md
└── src/
    ├── server.ts            # 入口：启动 HTTP 服务
    ├── app.ts               # Express 应用配置
    ├── config/
    │   └── index.ts         # 统一配置管理
    ├── constants/
    │   └── index.ts         # 业务常量、多维表格列映射与 SCHEMA（主表 + 记忆表）
    ├── types/
    │   └── index.ts         # TypeScript 类型 + Zod Schema
    ├── routes/
    │   └── index.ts         # 路由定义
    ├── controllers/
    │   └── feishu-event.controller.ts  # 飞书事件处理
    ├── services/
    │   ├── orchestrator.service.ts      # ⭐ 工作流编排器（记忆注入与写回）
    │   ├── jd-parser.service.ts
    │   ├── job-summary.service.ts
    │   ├── resume-advisor.service.ts
    │   ├── interview-generator.service.ts
    │   ├── memory.service.ts            # 记忆门面（读上下文、落 job、刷新摘要）
    │   ├── profile-memory.service.ts    # user_profile
    │   └── derived-memory.service.ts    # memory_summary（规则归纳）
    ├── integrations/
    │   ├── feishu/
    │   │   ├── auth.ts
    │   │   ├── message.ts
    │   │   ├── bitable.ts               # 主表 + 记忆表 API、自动补列、FeishuMemoryBitableService
    │   │   ├── bitable-memory.codec.ts  # 记忆字段编解码
    │   │   ├── task.ts
    │   │   └── document.ts
    │   └── llm/
    │       └── client.ts
    ├── prompts/
    │   ├── jd-parse.prompt.ts
    │   ├── summary.prompt.ts
    │   ├── resume-advice.prompt.ts
    │   ├── interview.prompt.ts
    │   └── light-memory.prompt.ts       # 轻量记忆 → Prompt 片段
    └── utils/
        ├── logger.ts
        ├── retry.ts
        └── validator.ts
```

## 🔧 本地启动

### 前置条件

- Node.js >= 18
- npm 或 yarn
- 飞书开放平台应用（已开通相关权限）
- LLM API Key（OpenAI / 火山方舟 / DeepSeek 等）

### 步骤

```bash
# 1. 克隆项目
git clone <repo-url> && cd jobpilot-feishu

# 2. 安装依赖
npm install

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的飞书和 LLM 配置

# 4. 开发模式启动（热重载）
npm run dev

# 5. 验证服务
curl http://localhost:3000/health
```

### 本地调试（不依赖飞书）

```bash
# 使用测试接口直接调用编排器（不传 userId，不启用记忆）
curl -X POST http://localhost:3000/api/test/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "jd_text": "岗位：高级前端工程师\n公司：字节跳动\n工作地点：北京\n\n岗位职责：\n1. 负责飞书文档前端架构设计与核心模块开发\n2. 推动前端工程化和性能优化\n3. 参与技术方案评审和代码 review\n\n任职要求：\n1. 本科及以上学历，3 年以上前端开发经验\n2. 精通 React/Vue，熟悉 TypeScript\n3. 有富文本编辑器或协同编辑经验优先\n4. 良好的沟通能力和团队协作精神"
  }'
```

## 🌐 环境变量说明

| 变量 | 必填 | 说明 |
|------|------|------|
| `FEISHU_APP_ID` | ✅ | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | ✅ | 飞书应用 App Secret |
| `FEISHU_VERIFICATION_TOKEN` | ✅ | 事件订阅验证 Token |
| `FEISHU_ENCRYPT_KEY` | ❌ | 事件加密 Key |
| `FEISHU_BITABLE_APP_TOKEN` | ✅ | **主业务**多维表格 App Token |
| `FEISHU_BITABLE_TABLE_ID` | ✅ | **主业务**数据表 Table ID |
| `FEISHU_MEMORY_BITABLE_APP_TOKEN` | ❌ | 记忆库 App Token；不填则与主表同 App |
| `FEISHU_MEMORY_USER_PROFILE_TABLE_ID` | ❌ | 画像表；三张记忆表**须同时配齐**才启用记忆 |
| `FEISHU_MEMORY_JOB_RECORDS_TABLE_ID` | ❌ | 岗位过程表 |
| `FEISHU_MEMORY_SUMMARY_TABLE_ID` | ❌ | 周期摘要表 |
| `FEISHU_DOC_FOLDER_TOKEN` | ❌ | 文档存放目录 Token |
| `LLM_API_BASE_URL` | ✅ | LLM API 地址 |
| `LLM_API_KEY` | ✅ | LLM API Key |
| `LLM_MODEL` | ❌ | 模型名称（默认 gpt-4o） |

## 🔗 飞书集成配置指南

### 1. 创建飞书应用

1. 登录 [飞书开放平台](https://open.feishu.cn)
2. 创建企业自建应用
3. 记录 App ID 和 App Secret

### 2. 配置权限

在应用的「权限管理」中开通以下权限：

- `im:message:send_as_bot` — 以应用身份发送消息
- `im:message` — 接收消息事件
- `bitable:app` — 多维表格读写
- **「新增/编辑字段」类权限**（名称以控制台为准，用于自动补列；无则自动建列失败时仅降级打日志，主流程仍继续）
- `task:task:write` — 创建任务
- `docx:document` — 创建文档
- `drive:drive` — 云文档操作

### 3. 配置事件订阅

1. 进入「事件订阅」页面
2. 请求地址填入：`https://your-domain.com/webhook/feishu`
3. 添加事件：`接收消息 im.message.receive_v1`
4. 记录 Verification Token

### 4. 多维表格（主表 + 记忆表）

#### 主业务台账表（必填）

指向 `FEISHU_BITABLE_*`。**推荐**预先按下列列名建表（`投递状态` 可为单选或文本；单选需含常用选项）。若未建全列，服务在 **每次 `addRecord` 前** 会尝试自动创建缺失列（默认多为「文本」，`创建时间` 为「日期」）。

| 字段名 | 建议类型 |
|--------|----------|
| 公司名称 | 文本 |
| 岗位名称 | 文本 |
| 工作地点 | 文本 |
| 级别要求 | 文本 |
| 核心技能 | 文本 |
| 岗位总结 | 文本 |
| 简历建议 | 文本 |
| 面试题 | 文本 |
| 投递状态 | 单选或文本 |
| 创建时间 | 日期 |
| 来源 | 文本 |

从多维表格 URL 中获取 `app_token` 和 `table_id` 填入 `.env`。

#### 求职记忆三张表（可选）

在**同一或不同**多维表格应用中创建三个数据表，将 Table ID 填入 `FEISHU_MEMORY_*`。列名需与 `src/constants/index.ts` 中 `MEMORY_*_FIELD_MAP` 一致；亦可先建空表，由服务在 **首次读写前** 按 `MEMORY_*_SCHEMA` 自动补列（详见上文「记忆三张表自动补列」）。

### 5. 公网暴露（开发调试）

```bash
# 使用 ngrok 暴露本地端口
ngrok http 3000
# 将生成的 https URL 填入飞书事件订阅的请求地址
```

## 🎬 演示流程

```
用户                          JobPilot                        飞书生态
 │                               │                               │
 │  发送 JD 文本到飞书聊天       │                               │
 │──────────────────────────────>│                               │
 │                               │                               │
 │  收到「处理中」提示           │                               │
 │<──────────────────────────────│                               │
 │                               │                               │
 │                               │── LLM: JD 结构化解析 ──>     │
 │                               │──（可选）读记忆表 ────────>   │
 │                               │── LLM: 总结/简历/面试（带记忆）│
 │                               │                               │
 │                               │── 主表 addRecord（先补列）──>│
 │                               │──（可选）写记忆表 ────────>   │
 │                               │── 创建跟进任务 ─────────────>│
 │                               │── 创建面试准备文档 ────────>│
 │                               │                               │
 │  收到完整分析结果             │                               │
 │<──────────────────────────────│                               │
```

## 📦 示例响应

```
✅ 岗位分析完成
━━━━━━━━━━━━━━━━━━

🏢 字节跳动 · 高级前端工程师
📍 北京
📊 高级
🔑 核心技能：React、TypeScript、前端架构、性能优化、富文本编辑器、协同编辑

📋 【岗位要求总结】
该岗位主要负责飞书文档的前端架构设计与核心开发，最看重 React/TS 深度、
架构设计能力、性能优化经验。适合有 3 年以上经验、对富文本/协同编辑有
研究的前端工程师。投递时应重点强调大型前端项目架构经验和性能调优成果。

✏️ 【简历修改建议】
1. 在项目经历中突出你参与过的最复杂前端架构项目...
2. 确保简历中明确列出 React、TypeScript 等关键词...
...

🎯 【可能面试题】
Q1: 请描述你做过的最有挑战性的前端架构设计...
  💡 意图：考察架构能力和技术深度
  📝 要点：描述背景和约束；架构选型过程；最终效果和数据

━━━━━━━━━━━━━━━━━━
📊 执行状态：
  ✅ 多维表格已写入
  ✅ 跟进任务已创建
  ✅ 面试准备文档已生成

📄 面试准备文档：https://feishu.cn/docx/xxxxx

💪 祝你求职顺利！有新的 JD 随时发给我。
```

## 🔮 后续扩展方向

1. **简历匹配度评分**：上传简历文件，自动与 JD 匹配打分
2. **多 JD 批量处理**：支持批量粘贴多个 JD 并行分析
3. **投递状态流转**：在多维表格中更新状态时触发下一步自动化
4. **面试日历管理**：自动创建日历事件并提醒准备
5. **求职数据看板**：基于多维表格生成求职进展统计
6. **记忆摘要 LLM 版**：在可解释的规则摘要之上叠加短 LLM 润色（需单独降级策略）

## 📄 License

MIT
