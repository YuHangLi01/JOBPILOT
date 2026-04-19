# knowledge-base/ — 知识库灌库流水线

把 P2.1 产出的数据（labeled JD、结构化面经、Markdown 简历）切片并灌入
`jd_kb` / `interview_kb` / `user_kb` 三个 Milvus 集合，直接复用 `python-agent`
的 `jobpilot_agent.retrieval` 层（Hybrid Dense + BM25 + RRF）。

## 目录布局

```
knowledge-base/
├── pyproject.toml                      # 独立 uv 包，依赖 ../python-agent（path dep）
├── Dockerfile                          # 两阶段 uv 构建，entrypoint=kb-ingest
├── README.md
├── data/
│   ├── labeled/jd_labeled.jsonl               # P2.1 产出：500 条 JD
│   ├── clean/interview_structured_filtered.jsonl  # P2.1 产出：643 条面经
│   ├── user_samples/*.md                      # 4 份示例简历（演示）
│   ├── ingest_report_*.json                   # 灌库报告（自动生成）
│   └── retrieval_smoke_report.md              # 召回 smoke 报告（自动生成）
├── src/kb_builder/
│   ├── models.py                       # LabeledJD / StructuredInterview / *Chunk / IngestReport
│   ├── extractors/jd_fields.py         # 从 jd_text 正则抽取 company/position/location
│   └── ingest/
│       ├── splitters/                  # jd / interview / user 三个 splitter
│       ├── orchestrator.py             # KnowledgeBaseBuilder
│       └── cli.py                      # kb-ingest CLI
└── tests/
    ├── test_splitters.py               # 单测（无需 Milvus）
    └── retrieval_smoke_test.py         # 20 case smoke（@pytest.mark.integration）
```

## 三个 Collection Schema 一览

| 字段 | `jd_kb` | `interview_kb` | `user_kb` |
|------|:-------:|:-------------:|:--------:|
| `doc_id` | `jd-{jd_id}-{chunk_index}` | `int-{interview_id}-{turn_id}` | `usr-{user_id}-{chunk_index}` |
| `text` | 分段后的 JD 文本 | 单条 turn 内容 | Markdown 小节 |
| `source_id` | `jd_id` | `interview_id` | `user_id` |
| `chunk_index` | 段落序号 | `turn_id` | 小节序号 |
| `company` | 正则抽取（可空） | 面经 meta | — |
| `position` | 正则抽取（可空，兜底用 `sub_type`） | 面经 meta | — |
| 动态字段 | `chunk_type`（responsibilities / requirements / perks / full）、`location`、`job_type`、`sub_type`、`level`、`locale`、`channel` | `role`、`stage`、`level`、`year`、`outcome`、`prev_turn_text`、`next_turn_text` | `user_id`、`doc_type`、`section`、`section_title` |

Milvus 集合启用 `enable_dynamic_field=True`，所有非显式字段自动写入动态字段，不
需要手改 schema。对应的 `MilvusVectorStore.search()` 在 P2.3 里已改为
`output_fields=["*"]`，过滤后的 `RetrievalResult.metadata` 会带回所有元数据。

## 灌库流程

### 1. 本地开发（Chroma 自动降级，无需 Milvus）

```bash
cd knowledge-base
uv sync
cp ../python-agent/.env.example .env  # 至少写入 LLM_API_KEY，RETRIEVAL_FALLBACK_TO_CHROMA=true
uv run kb-ingest rebuild-jd
uv run kb-ingest rebuild-interview
uv run kb-ingest rebuild-user
uv run kb-ingest stats
uv run pytest tests/test_splitters.py
```

### 2. Docker 一键灌库（推荐）

```bash
# 先起基础组件
docker compose up -d milvus

# 一次性跑 kb-ingester
docker compose --profile ingest up --build kb-ingester
# 默认 command 为 rebuild-all；如需单跑：
docker compose --profile ingest run --rm kb-ingester rebuild-jd
```

### 3. 召回 smoke 验证（需要 Milvus 灌库完成）

```bash
uv run pytest tests/retrieval_smoke_test.py -m integration -s
cat data/retrieval_smoke_report.md
```

验收标准：`pass_rate ≥ 85%`，平均延迟 `< 300 ms`。

## CLI 速查

```bash
kb-ingest rebuild-jd        [--input data/labeled/jd_labeled.jsonl] [--batch-size 50]
kb-ingest rebuild-interview [--input data/clean/interview_structured_filtered.jsonl]
kb-ingest rebuild-user      [--input-dir data/user_samples/]
kb-ingest rebuild-all
kb-ingest stats                     # 每个 collection 的向量数 + BM25 pickle 大小
kb-ingest drop-and-rebuild --yes    # 危险：先 drop 三个 collection 再全量重建
kb-ingest report --output data/kb_report.md
```

## 故障排查

| 症状 | 原因 | 解决 |
|------|------|------|
| `MilvusException: connect failed` | 容器未起或端口冲突 | `docker compose ps`；确认本机 19530 未被占用 |
| 首次 embedding 很慢 | 下载 BGE-M3 ≈2GB | 已在 compose 中默认 `HF_ENDPOINT=https://hf-mirror.com`；本地开发可 `export` 同名变量 |
| smoke test 通过率偏低 | 多半是分词 / filter 不命中 | 先跑 `python -m kb_builder.tests.retrieval_smoke_test` 打印详细 top-k，再决定调 tokenizer.TECH_TERMS 还是调整 case |
| BM25 跨进程丢失 | `bm25_index_dir` 在容器里未挂载 | 生产场景把 `bm25_index_dir` 指向挂载盘，或每次启动时自动 rebuild |

## 与 python-agent 的依赖

`pyproject.toml` 通过 `tool.uv.sources.jobpilot-agent.path = "../python-agent"`
以 editable 方式依赖 python-agent 包。修改检索层代码后，两边都即时生效。

注意 orchestrator 会触碰 `HybridRetriever._bm25`（一个下划线前缀的字段）来持
久化索引文件 —— 两端都是第一方代码，接受这个耦合；如果以后 retrieval 层要暴露
公共 `persist_bm25()` API，可一并替换。
