# portfolio_check

```yaml
name: portfolio_check
version: 0.1.0
tags: [external_api, llm]
dependencies: []
```

## 功能描述

读取用户飞书云文档作品集，对照 JD 要求分析：

- 作品集整体描述（项目数量、类型）
- 逐条 JD 要求的覆盖情况（covered + evidence / gap_suggestion）
- 整体覆盖度评分 [0, 1]
- 作品集呈现优化建议（3–5 条）

## 触发条件（should_invoke）

```
job_type in {product, design}
AND user_context.portfolio_doc_ref 非空（飞书云文档 token）
```

## 不触发条件

- tech 岗位（走 github_scan）
- 无 portfolio_doc_ref
- 非产品/设计岗位（运营/管理等）

## 架构约束

Python 不直接调飞书 API，通过 Node.js 内部接口代理：

```
PortfolioCheckSkill
  └─ FeishuProxyClient.read_doc(doc_token)
       └─ POST /internal/feishu/docs/read
            └─ Node.js FeishuDocumentService.readDocAsMarkdown()
                 └─ GET /docx/v1/documents/{token}/blocks
```

## 输出（PortfolioCheckData）

| 字段 | 类型 | 说明 |
|------|------|------|
| `portfolio_summary` | str | 作品集概述（≤ 200 字） |
| `case_count` | int | 项目案例数量 |
| `coverage_gaps` | list[PortfolioGap] | JD 逐条覆盖分析 |
| `coverage_score` | float (0–1) | 整体覆盖度 |
| `presentation_tips` | list[str] | 呈现优化建议（3–5 条） |

## 错误处理

- 飞书代理超时（15s）→ `SKILL_EXTERNAL_FAIL`
- Node.js 返回 HTTP 错误 → `SKILL_EXTERNAL_FAIL`
- LLM 超时 → `SKILL_TIMEOUT`
