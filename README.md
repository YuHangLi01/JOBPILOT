# 🚀 JobPilot for Feishu / 求职作战官

> 一个运行在飞书中的垂直场景办公 Agent，帮助求职者从「收到 JD」到「完成面试准备」的全流程提效。

## ✨ 项目亮点

- **聊天即触发**：在飞书对话中发送一段 JD，即可自动启动完整分析流程
- **LLM 编排引擎**：多步骤 Prompt 分离设计，结构化解析 → 总结 → 简历建议 → 面试题
- **飞书生态打通**：多维表格记录、任务创建、文档生成一步到位
- **优雅降级**：任一外部调用失败不影响主流程，用户始终获得最大可用结果
- **比赛就绪**：清晰的工程结构、完整类型定义、模块化设计，适合答辩展示

## 📋 功能概览

| 功能 | 描述 |
|------|------|
| JD 结构化解析 | 提取公司、岗位、职责、要求、技能等字段 |
| 岗位要求总结 | 100~200 字精炼总结，一目了然 |
| 简历修改建议 | 5~8 条针对性建议，可直接行动 |
| 面试题预测 | 3 道高概率面试题 + 出题意图 + 回答要点 |
| 多维表格写入 | 岗位信息自动存入飞书 Bitable，形成求职台账 |
| 跟进任务创建 | 自动创建带截止时间的飞书任务 |
| 面试准备文档 | 自动生成结构化文档并返回链接 |
| 结果消息回传 | 将全部结果以清晰格式推送到聊天 |

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
    │   └── index.ts         # 业务常量
    ├── types/
    │   └── index.ts         # TypeScript 类型 + Zod Schema
    ├── routes/
    │   └── index.ts         # 路由定义
    ├── controllers/
    │   └── feishu-event.controller.ts  # 飞书事件处理
    ├── services/
    │   ├── orchestrator.service.ts      # ⭐ 工作流编排器
    │   ├── jd-parser.service.ts         # JD 解析服务
    │   ├── job-summary.service.ts       # 岗位总结服务
    │   ├── resume-advisor.service.ts    # 简历建议服务
    │   └── interview-generator.service.ts # 面试题服务
    ├── integrations/
    │   ├── feishu/
    │   │   ├── auth.ts       # 飞书 Token 管理
    │   │   ├── message.ts    # 消息发送
    │   │   ├── bitable.ts    # 多维表格写入
    │   │   ├── task.ts       # 任务创建
    │   │   └── document.ts   # 文档创建
    │   └── llm/
    │       └── client.ts     # 统一 LLM 客户端
    ├── prompts/
    │   ├── jd-parse.prompt.ts       # JD 解析 Prompt
    │   ├── summary.prompt.ts        # 岗位总结 Prompt
    │   ├── resume-advice.prompt.ts  # 简历建议 Prompt
    │   └── interview.prompt.ts      # 面试题 Prompt
    └── utils/
        ├── logger.ts         # 日志工具
        ├── retry.ts          # 重试工具
        └── validator.ts      # 输入校验
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
# 使用测试接口直接调用编排器
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
| `FEISHU_BITABLE_APP_TOKEN` | ✅ | 多维表格 App Token |
| `FEISHU_BITABLE_TABLE_ID` | ✅ | 数据表 Table ID |
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
- `bitable:app` — 多维表格操作
- `task:task:write` — 创建任务
- `docx:document` — 创建文档
- `drive:drive` — 云文档操作

### 3. 配置事件订阅

1. 进入「事件订阅」页面
2. 请求地址填入：`https://your-domain.com/webhook/feishu`
3. 添加事件：`接收消息 im.message.receive_v1`
4. 记录 Verification Token

### 4. 创建多维表格

在飞书中创建一个多维表格，添加以下字段：

| 字段名 | 字段类型 |
|--------|----------|
| 公司名称 | 文本 |
| 岗位名称 | 文本 |
| 工作地点 | 文本 |
| 级别要求 | 文本 |
| 核心技能 | 文本 |
| 岗位总结 | 文本 |
| 简历建议 | 文本 |
| 面试题 | 文本 |
| 投递状态 | 单选（待投递/已投递/面试中/已拿 offer/已拒绝） |
| 创建时间 | 日期 |
| 来源 | 文本 |

从多维表格 URL 中获取 `app_token` 和 `table_id` 并填入 `.env`。

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
 │                               │── LLM: 生成岗位总结 ──>      │
 │                               │── LLM: 生成简历建议 ──>      │
 │                               │── LLM: 生成面试题 ──>        │
 │                               │                               │
 │                               │── 写入多维表格 ─────────────>│
 │                               │── 创建跟进任务 ─────────────>│
 │                               │── 创建面试准备文档 ────────>│
 │                               │                               │
 │  收到完整分析结果             │                               │
 │  （含文档链接、任务状态等）   │                               │
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
6. **智能跟进提醒**：根据投递时间自动发送跟进提醒
7. **模拟面试 Bot**：基于生成的面试题开展模拟对话练习
8. **团队协作模式**：支持 HR / 猎头使用同一系统管理候选人

## 📄 License

MIT
