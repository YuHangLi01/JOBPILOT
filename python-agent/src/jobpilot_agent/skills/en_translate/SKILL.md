# en_translate

```yaml
name: en_translate
version: 0.1.0
tags: [llm, translation, english, resume]
dependencies: []
```

## 功能描述

为英文岗位或外资公司 JD 生成：

1. **双语摘要**：英文摘要（150–300 词）+ 中文摘要（150–300 字）
2. **STAR 格式简历要点**：3–5 条针对该岗位的英文简历亮点
3. **ATS 关键词**：5–10 个高频岗位关键词，用于简历 ATS 优化
4. **语气风格评估**：formal / casual / technical / startup / enterprise

## 触发条件（should_invoke）

满足以下任一条件即触发：

```
locale == "en"                          # JD 语言/用户语言为英文
OR company in FOREIGN_COMPANIES         # 公司在外资名单中（子字符串匹配）
OR user_context.preferred_lang == "en"  # 用户明确偏好英文输出
```

## 不触发条件

- 纯中文岗位（locale=zh）
- 国内本土公司
- 用户未设置英文偏好

## 输出（EnTranslateData）

| 字段 | 类型 | 说明 |
|------|------|------|
| `jd_summary_en` | str | 英文摘要，150–300 词 |
| `jd_summary_zh` | str | 中文摘要，150–300 字 |
| `resume_bullets_en` | list[str] | STAR 格式英文简历要点（3–5 条） |
| `key_terms_en` | list[str] | ATS 关键词（5–10 个） |
| `tone` | str | 语气风格评估 |

## 外资公司名单

`FOREIGN_COMPANIES` 常量定义在 `index.py` 顶层，包含 Google、Microsoft、Amazon 等约 40 家常见外资企业，支持子字符串匹配（大小写不敏感）。

## 使用示例

```python
ctx = JDContext(
    request_id="req-001",
    user_id="u001",
    jd_text="We are looking for a Senior Software Engineer at Google...",
    parsed_jd={"company": "Google"},
    classification=JDClassification(locale="en", ...),
)
output = await skill.invoke(ctx)
print(output.data["jd_summary_en"][:100])  # "Google is seeking..."
print(output.data["resume_bullets_en"][0])  # "Designed and implemented..."
```
