# JobPilot Agent · 数据集说明

## 1. 总览

项目自建三份数据集 + 灌入三个 Milvus 向量库。所有数字可追溯到 `knowledge-base/data/` 下的 JSONL 原始文件。

| 数据集 | 规模 | 用途 | 来源 | 合规约束 |
|---|---|---|---|---|
| `jd_labeled.jsonl` | 500 条 | Skill 路由 ground truth + RAG 检索语料 | 公开 JD 清洗 + LLM 初标 + 人工复核 | 不含个人信息,非商用 |
| `interview_structured_filtered.jsonl` | 643 条 | Interview Replay 评估 + 面试 RAG 检索语料 | 公开面经清洗 + 结构化 | 不含个人信息,非商用 |
| `user_samples/*.md` | 4 份 | 个人 KB 演示样本 | 项目作者人工撰写 | 可公开 |

## 2. 合法性声明(首要)

**本项目数据集仅用于非商业研究与校园挑战赛评估,禁止公开分发、禁止商业使用。**

- 所有数据来源于公开网页(各大招聘平台 JD + 面经社区),遵守源站 `robots.txt`
- 清洗流程已剔除姓名、联系方式、简历 PII 等可识别字段
- 爬取请求频率 ≥ 3s(见 `knowledge-base/src/kb_builder/crawler/README.md`),不对源站造成压力
- 若收到任何源站的合理删除请求,24 小时内响应并从仓库移除
- 标注结果仅用于本项目评估,不再外发

---

## 3. 数据集 1:JD 路由数据集

### 3.1 路径与 Schema

文件:`knowledge-base/data/labeled/jd_labeled.jsonl`
条数:500

```jsonc
{
  "jd_id": "a1b2c3d4",              // 8 位 hash
  "jd_text": "职位：高级前端工程师...", // 原始 JD 正文
  "labels": {
    "job_type": "tech",             // tech / ops / mgmt / design / operations
    "sub_type": "frontend",         // 自由文本(词表在演进中)
    "level": "senior",              // intern / junior / middle / senior / lead
    "locale": "zh",                 // zh / en / mixed
    "channel": "social"             // campus / social
  },
  "expected_skills": ["tech_stack_extract", "interview_rag"],
  "forbidden_skills": ["en_translate", "gpa_check", "github_scan"],
  "annotator": "llm+human",
  "confidence": 0.92                // 标注一致性自评
}
```

### 3.2 获取流程

1. **抓取**:`kb-build crawl` 从 HuggingFace `jobs.csv` 等公开源抽取原始 JD
2. **清洗**:`kb-build clean` 去重、正则抽取 company/position/location、剔除 PII
3. **LLM 初标**:`kb-build llm-annotate` 用 deepseek-chat 按 5 维标签打标
4. **人工复核**:`kb-build import-review` 人工复核 30 条高分歧样本,约 12.4% 改动率

### 3.3 分布统计(v1.0)

500 条分布(源自 `evaluation/reports/scenario_a_v1.md` §1 混淆矩阵对角线 + ground truth 计数):

- `job_type`:tech 占主(≈60%)、ops、mgmt、design
- `level`:junior/middle 合计 > 70%(校园+社招主力)
- `locale`:zh ≈95%, en ≈5%
- `channel`:social ≈60%, campus ≈40%

混淆矩阵图:`python-agent/evaluation/reports/figures/classification_confusion_matrix_*.png`

### 3.4 标注一致性

LLM 初标 → 人工复核改动率 **12.4%**(低于 20% 目标,视为合格)。
主要分歧源:`sub_type` 自由文本字段("backend_dev" vs "backend_engineer" 一类近义词)。

### 3.5 复现命令

```bash
cd knowledge-base
kb-build crawl --source hf --path ~/Downloads/jobs.csv --out data/raw/
kb-build clean   --in data/raw/  --out data/clean/
kb-build llm-annotate --in data/clean/ --out data/labeled/jd_llm_labeled.jsonl
kb-build import-review --in data/labeled/jd_llm_labeled.jsonl \
                       --review data/labeled/human_review.csv \
                       --out data/labeled/jd_labeled.jsonl
```

---

## 4. 数据集 2:结构化面经数据集

### 4.1 路径与 Schema

文件:`knowledge-base/data/clean/interview_structured_filtered.jsonl`
条数:643(原始 ≈900 条,经 `quality_score` 过滤后保留)

```jsonc
{
  "interview_id": "f8e9d7c6",
  "company": "字节跳动",           // "unknown" 约占 X%
  "position": "高级前端工程师",
  "level": "senior",
  "year": 2024,
  "turns": [
    {"turn_id": 1, "role": "interviewer", "content": "先自我介绍一下", "stage": "intro"},
    {"turn_id": 2, "role": "candidate", "content": "我毕业于...", "stage": "intro"},
    {"turn_id": 3, "role": "interviewer", "content": "聊聊你最自豪的项目", "stage": "project_deep_dive"}
    // ...
  ],
  "outcome": "offer",              // offer / pass / unknown
  "stage_labels": {"intro": 2, "project_deep_dive": 6, "tech_qa": 18, "scenario": 4, "reverse": 2},
  "quality_score": 0.82            // 结构化清晰度评分(0-1)
}
```

### 4.2 用途

- **Replay 评估**:从 turn 列表里取"前 N turn → next turn"构成 pair,评估 Bot 下一问预测能力。300 条样本抽取 30 对 pair(`replay_evaluation_v1.md` §摘要)。
- **Stage 预测评估**:300 条面经按 turn 粒度抽取 stage 标签样本。
- **interview_kb RAG 语料**:all turns 灌入 Milvus `interview_kb`。

### 4.3 已知局限

- `company="unknown"` 约占 24/30(Replay 抽样集,见 `replay_evaluation_v1.md` §4),多来自 HF 公开 QA 题库。不影响按 stage 过滤的召回。
- `closing` / `reverse` 阶段样本量少(stage_prediction_v1.md 中 closing 支持数为 0),这两个阶段评估方差较大,是下一版迭代目标。

### 4.4 复现命令

```bash
cd knowledge-base
kb-build interview-crawl --source hf --path ~/Downloads/interviews.csv --out data/raw/
kb-build interview-clean --in data/raw/ --out data/clean/interview_structured.jsonl
kb-build interview-filter --in data/clean/interview_structured.jsonl \
                          --min-quality 0.6 \
                          --out data/clean/interview_structured_filtered.jsonl
```

---

## 5. 数据集 3:用户个人知识库样本

`knowledge-base/data/user_samples/`:4 份 Markdown 简历,H2/H3 层级,演示用,人工撰写。

**注意**:`u_default_resume.md` 必须包含"JobPilot"关键词,否则 smoke test `query="JobPilot 项目"` 会失败(见 `python-agent/src/jobpilot_agent/retrieval/README.md`)。

---

## 6. 灌库后:三个 Milvus Collection

```bash
docker compose up -d milvus
docker compose --profile ingest up --build kb-ingester   # rebuild-all
```

| Collection | 预期向量数 | 主要动态字段 | 典型过滤器 |
|---|---|---|---|
| `jd_kb` | ≥ 1500(500 × avg 3 chunk) | `chunk_type/job_type/sub_type/level/locale/channel/location` | `job_type=tech`, `sub_type=frontend` |
| `interview_kb` | ≥ 3000(643 × avg 10 turn) | `role/stage/level/year/outcome/prev_turn_text/next_turn_text` | `stage=tech_qa`, `company=字节跳动` |
| `user_kb` | ≥ 20(4 × avg 8 section) | `user_id/doc_type/section/section_title` | `user_id=u_default`, `section=projects` |

向量维度统一 **1024**(BGE-M3 本地 or Doubao 远程)。Milvus HNSW:`M=16, efConstruction=200, ef=64`。

---

## 7. 数据血缘图

```text
原始抓取(HF / 公开爬取)
        │
        ▼  (kb-build crawl + clean, PII 清洗)
labeled/*.jsonl     clean/*.jsonl     user_samples/*.md
        │
        ▼  (kb-ingest: splitter → embed → HybridRetriever.add_documents)
Milvus: jd_kb / interview_kb / user_kb
        │
        ▼  (python-agent/src/jobpilot_agent/retrieval/)
search_jd_kb / search_interview_kb / search_user_kb
        │
        ▼  (各 Skill / 面试子图调用)
LLM prompt 增强
```

---

## 8. 版本管理

- 采用 Git LFS 追踪(JSONL ≈ 数 MB 级)
- 语义化版本:
  - `v1.0` · 2026-04 · 首次完整标注,用于 Week 3 场景 A 评估
  - `v1.x` · 后续按议题小步迭代
- 每次版本化都会在 `knowledge-base/CHANGELOG.md` 记录改动范围与样本数

---

## 9. 数据质量备注

- **labeled JD** 顶层无 `company/position/location`:由 ingest 阶段正则抽取(`kb_builder/extractors/jd_fields.py`),未命中留空。后续如替换 labeling pipeline,可在 `LabeledJD` schema 上加这三字段。
- **structured interview** `company="unknown"` 约 24/30(Replay 抽样),多为 HF QA 题库源。按 `stage`/`role` 过滤的召回不受影响。
- **user_samples** 是 demo 用途,不要替换为真实简历 —— 会污染评估。
