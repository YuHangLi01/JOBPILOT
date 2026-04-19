# 李沐桐 — 高级软件工程师

## 基本信息

- 姓名：李沐桐
- 邮箱：limutong@example.com
- 电话：+86 138-0000-0011
- 所在城市：北京（朝阳区）
- 求职方向：高级 / 资深后端工程师、AI Infra、求职 SaaS 产品工程
- 期望城市：北京、上海、杭州、远程

## 教育经历

### 北京理工大学

- 软件工程 · 硕士 · 2018.09 – 2021.06
- GPA 3.78 / 4.0（专业前 10%）
- 研究方向：大规模检索系统与分布式缓存一致性
- 代表论文：一作《基于分层一致性哈希的多租户向量检索调度》

### 华中科技大学

- 计算机科学与技术 · 学士 · 2014.09 – 2018.06
- GPA 3.63 / 4.0
- ACM-ICPC 区域赛银牌，校内算法竞赛一等奖

## 工作经历

### 字节跳动 — Lark / 飞书办公套件

- 2023.07 – 至今 · 高级后端工程师 · 北京
- 负责飞书开放平台多维表格写入通道的可用性治理，主导「幂等写入 + 重放队列」方案，事故率从 0.6% 下降到 0.05%。
- 设计了企业文档 OCR 流水线的回源策略：冷数据统一回源到多可用区对象存储，P99 读延迟下降 38%。
- Owner：webhook 事件订阅重试、乘客级限流与灰度发布配置，覆盖 2000 万 MAU。

### 美团 — 到店事业群 · 搜索与推荐

- 2021.07 – 2023.06 · 后端工程师 → 高级后端工程师 · 北京
- 负责「搜索特征抽取」离线管道：日 1.2B 事件，用 Flink + Hudi 实现分钟级回灌。
- 与算法团队合作落地近线向量召回链路，首次引入 Milvus 2.x，单集群承载 5 亿向量，召回 P95 < 120ms。
- 推动内部召回 SDK 开源化（内部 GitLab 150+ star），获 2022 Q3 团队 OKR 绩效 S 评级。

## 项目经验

### JobPilot — 飞书求职作战 Agent（开源副业项目）

- 2024.11 – 至今 · 个人发起 + 3 人小团队
- 目标：把 LLM 能力嵌入飞书群聊，用户发 JD 就能得到「岗位解读 + 简历建议 + 模拟面试 + 跟进任务」四位一体的输出。
- 架构：Node.js Gateway（飞书侧副作用）+ Python Agent（LangGraph 编排 + RAG）+ OpenAPI 契约驱动类型同步。
- 我负责：整体架构设计、Python Agent 的 RAG 层（BGE-M3 稠密 + BM25 稀疏 + RRF 融合 + BGE Reranker），以及「JD 路由」子图的 LLM 编排。
- 数据：自构建 JD 500 条 + 面经 643 条 + 简历范例，接入 Milvus 混合检索。
- 关键结果：JD 分析端到端耗时 < 25 秒；平均 Top-3 命中率 91.2%；累计触达 150+ 测试用户。

### 多租户向量检索中台（美团内部）

- 2022.04 – 2023.03 · 技术负责人
- 场景：为搜索、广告、风控等 7 个业务线提供统一的向量检索 API，SLA 99.95%。
- 关键决策：基于一致性哈希 + Raft 的 shard 调度策略，写入链路引入背压队列。
- 影响：机器成本节约 42%，业务接入工期从平均 3 周降至 2.5 天。

### 内部文档智能检索助手（字节跳动 · 飞书 Hackathon 2024 银奖）

- 一周内完成的黑客松作品：将 Lark 企业知识库切片后接入 Milvus + LLM，员工自然语言问答命中内部 Wiki 的准确率从 61% 提升到 87%。

## 技能

- **语言**：Python（主力）、Go、TypeScript、Java（工程级）。
- **后端 / Infra**：FastAPI、Gin、gRPC、Kubernetes、Istio、Kafka、Flink、PostgreSQL、Redis、ClickHouse。
- **AI / RAG**：LangChain、LangGraph、pymilvus、sentence-transformers、BGE-M3、jieba、BM25Okapi、BGE Reranker、OpenAI 兼容 API（火山方舟 / OpenAI）。
- **工程素养**：OpenAPI 契约驱动开发、全链路可观测性（OpenTelemetry）、Trunk-based 开发、PR 文化。
- **语言与证书**：英语 CET-6（600）、TOEFL 94、AWS Certified Solutions Architect – Associate。

## 其他

- 技术博客 `limutong.dev` 近一年 12 篇 RAG / 向量检索主题长文，单篇 Top 1 阅读量 42k。
- GitHub：https://github.com/limutong（JobPilot 主仓库、Milvus 中文文档贡献 20+ PR）。
- 业余爱好：公路骑行（年均 3500km）、写作、开源文档翻译。
