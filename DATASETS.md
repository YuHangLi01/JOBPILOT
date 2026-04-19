# JobPilot Datasets

本仓库在 `knowledge-base/` 下维护三份离线数据 + 三个 Milvus 集合，二者通过
`kb-ingest` 管线衔接（见 [`knowledge-base/README.md`](./knowledge-base/README.md)）。

## 原始数据（P2.1 产出）

| 路径 | 条数 | Schema |
|------|------|--------|
| `knowledge-base/data/labeled/jd_labeled.jsonl` | 500 | `{jd_id, jd_text, labels:{job_type, sub_type, level, locale, channel}, expected_skills, forbidden_skills, annotator, confidence, ...}` |
| `knowledge-base/data/clean/interview_structured_filtered.jsonl` | 643 | `{interview_id, company, position, level, year, turns:[{turn_id, role, content, stage}], outcome, stage_labels, quality_score}` |
| `knowledge-base/data/user_samples/*.md` | 4 | Markdown 简历，H2/H3 层级 |

## 灌库后三个 Milvus Collection

灌库方式：
```bash
docker compose up -d milvus
docker compose --profile ingest up --build kb-ingester   # rebuild-all
```

| Collection | 预期向量数 | 主要动态字段 | 典型过滤器 |
|-----------|----------|-------------|-----------|
| `jd_kb` | ≥ 1500（500 JD × 平均 3 段） | `chunk_type`, `job_type`, `sub_type`, `level`, `locale`, `channel`, `location` | `job_type=tech`, `sub_type=frontend` |
| `interview_kb` | ≥ 3000（643 面经 × 平均 10 turn） | `role`, `stage`, `level`, `year`, `outcome`, `prev_turn_text`, `next_turn_text` | `stage=tech_qa`, `company=字节跳动` |
| `user_kb` | ≥ 20（4 份简历 × 平均 8 小节） | `user_id`, `doc_type`, `section`, `section_title` | `user_id=u_default`, `section=projects` |

向量维度统一 1024（BGE-M3 本地）。Milvus HNSW `M=16, efConstruction=200, ef=64`。

## 数据血缘

```
原始抓取 / HF 数据集
      │
      ▼  (P2.1 过滤 + LLM / 规则打标)
labeled/*.jsonl   clean/*.jsonl   user_samples/*.md
      │
      ▼  (P2.3 kb-ingest splitter → HybridRetriever.add_documents)
Milvus: jd_kb / interview_kb / user_kb
      │
      ▼  (python-agent/src/jobpilot_agent/retrieval)
search_jd_kb / search_interview_kb / search_user_kb
```

## 数据质量备注

- **labeled JD** 目前无顶层 `company` / `position` / `location`；这些字段由
  ingest 阶段的正则 best-effort 抽取（见 `kb_builder/extractors/jd_fields.py`），
  未命中时留空。后续如有更稳的 labeling pipeline，可覆盖 `LabeledJD` 的 schema。
- **structured interview** 中 `company="unknown"` 的条目约 XX%（多为 HF QA 题库
  源），不影响 `stage` / `role` 相关召回。
- **user_samples** 是演示用，内容人工撰写；`u_default_resume.md` 需包含「JobPilot」
  项目，否则 smoke test `query="JobPilot 项目"` 会失败。
