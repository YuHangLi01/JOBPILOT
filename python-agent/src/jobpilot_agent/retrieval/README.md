# retrieval/ — RAG 检索层

## 分层架构

```
对外接口（下游调用点）
──────────────────────────────────────────────────────────────
  HybridRetriever.search(query, collection, options)
         │
         ├─ BaseEmbedder.embed_texts(query)
         │      └─ BGEM3Embedder（本地）/ DoubaoEmbedder（远程）
         │           └─ MilvusVectorStore.search()
         │                   └─→ dense_results[top_N]
         │
         ├─ tokenizer.tokenize_for_bm25(query)
         │      └─ BM25Index.search()
         │                   └─→ sparse_results[top_N]
         │
         ├─ RRFRanker.rank() / WeightedRanker.rank()
         │           └─→ fused_results[top_K_fused]
         │
         └─ (可选) BGEReranker.rerank()
                     └─→ final_results[top_k]

降级路径：Milvus 不可用时 get_vector_store() 自动返回 ChromaVectorStore
──────────────────────────────────────────────────────────────
```

## 文件说明

| 文件 | 职责 |
|------|------|
| `types.py` | `Document`, `RetrievalResult`, `SearchOptions`, `CollectionName` |
| `tokenizer.py` | jieba 中文分词，TECH_TERMS 自定义词典，`tokenize_for_bm25()` |
| `base.py` | `BaseRetriever` ABC，定义 `search()` 和 `add_documents()` 接口 |
| `embedding.py` | `BaseEmbedder`, `BGEM3Embedder`, `DoubaoEmbedder`, `get_embedder()` |
| `bm25.py` | `BM25Index`，内存 BM25Okapi，pickle 持久化 |
| `vector_store.py` | `MilvusVectorStore`, `ChromaVectorStore`, `get_vector_store()` |
| `rrf_ranker.py` | `RRFRanker`（`1/(k+rank)` 公式）, `WeightedRanker` |
| `reranker.py` | `BGEReranker`，Cross-Encoder 精排 |
| `hybrid_retriever.py` | `HybridRetriever`（实现 `BaseRetriever`），`get_retriever()` 工厂 |
| `__init__.py` | 统一导出所有公开 API |

## 核心数据流

### 写入文档

```
Document(doc_id, collection, text, metadata)
    │
    ├─ embedder.embed_texts([text]) → ndarray(N, 1024)
    ├─ vector_store.upsert(collection, docs, embeddings)
    └─ bm25_index.add_or_update(docs)
```

### 检索文档

```
query: str
    │
    ├─ embed_one(query) ──────────────────────────────────────┐
    │                                                          ▼
    │                                              vector_store.search()
    │                                                  dense_results
    │
    ├─ tokenize_for_bm25(query) ──────────────────────────────┐
    │                                                          ▼
    │                                              BM25Index.search()
    │                                                  sparse_results
    │
    └─ RRFRanker.rank(dense_results, sparse_results, top_k)
               └─ (可选) BGEReranker.rerank()
                            └─ list[RetrievalResult]
```

## 集合设计

| CollectionName | 用途 | 推荐 metadata 字段 |
|---------------|------|-------------------|
| `jd_kb` | JD（职位描述）知识库 | `company`, `position`, `level`, `source_id`, `chunk_index` |
| `interview_kb` | 面经知识库 | `company`, `position`, `stage`, `source_id`, `chunk_index` |
| `user_kb` | 用户简历知识库 | `user_id`, `resume_id`, `chunk_index` |

## 调优参数指南

### RRF k 值（`rrf_ranker.py: RRFRanker(k=60)`）

k 值控制排名融合的"平均程度"：

- **k 越小（如 k=1）**：第 1 名的 RRF 分远高于第 2 名，结果更"激进"，头部集中
- **k 越大（如 k=100）**：各名次 RRF 分差距变小，结果更"平均"，有利于长尾召回
- **k=60**：Cormack et al. 2009 论文推荐值，大多数场景表现稳定

**调试建议**：先跑 top-10，打印每条结果的 `rank_in_dense` 和 `rank_in_sparse`；
如果 dense 召回的相关文档总在 sparse top-1，但融合后排名下降，说明 k 偏大，可尝试 k=30。

### HNSW M 和 ef 参数（`vector_store.py`）

```python
# 当前配置
index_params = {"M": 16, "efConstruction": 200}
search_params = {"ef": 64}
```

| 参数 | 说明 | 调大的代价 |
|------|------|-----------|
| `M` | 每个节点的出度（连接数），默认 16 | 内存占用线性增加，构建更慢 |
| `efConstruction` | 构建时的动态候选集大小，默认 200 | 构建更慢，召回率更高 |
| `ef`（搜索时） | 搜索时的动态候选集，默认 64 | 搜索更慢，召回率更高 |

**500~5000 条规模**：M=16, efConstruction=200, ef=64 已足够，无需调整。
**10 万条以上**：考虑 M=32, efConstruction=400。

### BM25 k1 和 b 参数

`rank_bm25.BM25Okapi` 默认 k1=1.5, b=0.75（Okapi BM25 标准值）：

- **k1**：词频饱和参数。k1=0 → TF 贡献为 0（等价于 binary）；k1 越大 → TF 贡献越大
- **b**：文档长度归一化。b=0 → 不归一化；b=1 → 完全归一化
- **短文档集（< 200 字）**：可尝试 b=0.5 减少长度惩罚

如需调整，在 `BM25Index.build()` 中：
```python
self._bm25 = BM25Okapi(self._doc_tokens, k1=1.2, b=0.5)
```

## FAQ

### Q: Milvus 启动不了怎么办？

`get_vector_store()` 在探活失败且 `RETRIEVAL_FALLBACK_TO_CHROMA=true`（默认）时，
会自动切换到 `ChromaVectorStore`，使用本地磁盘存储（`./data/chroma`）。

验证降级是否生效：
```python
from jobpilot_agent.retrieval.vector_store import get_vector_store
vs = get_vector_store()
print(type(vs).__name__)  # 应输出 ChromaVectorStore
```

如需强制禁用降级（生产环境），设置 `RETRIEVAL_FALLBACK_TO_CHROMA=false`。

---

### Q: Embedding 模型（BGE-M3）下载很慢？

设置 HuggingFace 国内镜像：
```bash
export HF_ENDPOINT=https://hf-mirror.com
uv run uvicorn jobpilot_agent.main:app --reload
```

或者在 `.env` 中加：
```
HF_ENDPOINT=https://hf-mirror.com
```

模型约 2GB，首次下载后缓存在 `~/.cache/huggingface/`。

---

### Q: 检索结果不准，怎么排查？

按以下步骤逐层诊断：

1. **先看分词**（排查 BM25 召回问题）：
   ```python
   from jobpilot_agent.retrieval.tokenizer import tokenize_for_bm25
   print(tokenize_for_bm25("你的 query"))
   # 检查技术词是否被拆散，如果是，在 TECH_TERMS 里加该词
   ```

2. **单独跑两路**（排查哪路有问题）：
   ```python
   dense_results = await retriever._dense_search(query, SearchOptions(dense_top_k=10))
   sparse_results = await retriever._sparse_search(query, SearchOptions(sparse_top_k=10))
   print([r.doc_id for r in dense_results[:5]])
   print([r.doc_id for r in sparse_results[:5]])
   ```

3. **调整融合比例**（两路都没问题但融合排名不对）：
   尝试 `WeightedRanker(dense_weight=0.3, sparse_weight=0.7)` 加大 BM25 权重（适合关键词匹配场景），
   或反之加大 dense 权重（适合语义相似场景）。

4. **开启精排**（Top-10 里有相关文档但排名不靠前）：
   设置 `SearchOptions(enable_rerank=True, rerank_top_k=10)`，
   Cross-Encoder 的语义理解能力比双塔模型强得多。

---

### Q: 如何替换 Embedding 模型？

1. 修改 `.env`：
   ```
   EMBEDDING_PROVIDER=doubao
   # 或
   EMBEDDING_PROVIDER=local
   EMBEDDING_MODEL_NAME=BAAI/bge-large-zh-v1.5
   EMBEDDING_DIMENSION=1024
   ```

2. **注意**：更换模型后，已存储的向量与新模型不兼容，需要：
   - 清空 Milvus collection：`MilvusVectorStore.drop()`
   - 重新写入所有文档：`retriever.add_documents()`

---

### Q: 如何持久化 BM25 索引，避免重启后重建？

在应用启动时加载，入库后保存：
```python
from jobpilot_agent.retrieval.bm25 import BM25Index
from jobpilot_agent.retrieval.types import CollectionName

BM25_PATH = "./data/bm25_indexes/jd_kb.pkl"

try:
    bm25 = BM25Index.load(BM25_PATH)
except FileNotFoundError:
    bm25 = BM25Index(CollectionName.JD_KB)

# ... 写入文档后 ...
bm25.save(BM25_PATH)
```
