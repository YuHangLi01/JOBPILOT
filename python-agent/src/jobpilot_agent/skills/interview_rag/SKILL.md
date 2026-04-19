# interview_rag

```yaml
name: interview_rag
version: 0.1.0
tags: [rag, retrieval]
dependencies: []
```

## 功能描述

基于公司/岗位/阶段从面经知识库（`INTERVIEW_KB`）检索真实历史面试题，通过 LLM 改写生成针对性准备清单。

每道输出题目包含：
- 题目文本
- 来源公司 + 面试阶段
- 出题意图（具体考察哪种能力）
- 回答要点（3–5 条，可直接练习）
- `rag_source_doc_ids`（溯源，防止 LLM 幻觉）

## 触发条件（should_invoke）

```
parsed_jd.get("company") OR parsed_jd.get("position") 非空
```

## 不触发条件

- JD 文本过短，无法解析 company 或 position
- parsed_jd 为空字典

## 检索策略（双路并发）

```
query = "{company} {position} 面试"

├─ search_interview_kb(stage="tech_qa",          top_k=8)
└─ search_interview_kb(stage="project_deep_dive", top_k=5)
        │
        ▼ 按 doc_id 去重（保留高分副本）
        │
        ▼ 若结果为空 → 降级返回 coverage_note（不调 LLM）
        │
        ▼ LLM 改写 → InterviewRagData
```

## 输出（InterviewRagData）

| 字段 | 类型 | 说明 |
|------|------|------|
| `retrieved_count` | int | 去重后面经片段数 |
| `questions` | list[InterviewQuestion] | 生成的面试题（5–8 道） |
| `coverage_note` | str \| None | 检索说明 |
| `retrieval_metadata` | dict | tech_qa_hits / project_hits / avg_score |

## 降级策略

- Milvus 无数据时：返回 `questions=[]` + `coverage_note="未命中..."` + `success=True`（不报错）
- RAG 超时时：整体超时 → `SKILL_TIMEOUT`

## 反模式

- 不在本层重新实现检索逻辑，直接调用 `search_interview_kb()`
