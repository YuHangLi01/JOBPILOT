# gpa_check

```yaml
name: gpa_check
version: 0.1.0
tags: [llm, campus, gpa, education]
dependencies: []
```

## 功能描述

检测校招 JD 中的 GPA / 绩点 / 学历门槛要求，识别：

- **显性要求**：JD 明文写出（如 "GPA ≥ 3.5/5.0"、"985/211 毕业"）
- **隐性要求**：上下文推断（如 "优秀应届生" 隐含高绩点期望）

## 触发条件（should_invoke）

```
channel == "campus"
AND JD 包含信号词（GPA|绩点|985|211|双一流|学历|成绩|专业排名|硕士|博士）
```

## 不触发条件

- 社会招聘渠道（channel != "campus"）
- JD 中无任何学历相关信号词

## 双路策略

```
JD 文本
  │
  ├─ [正则] regex_rules.extract_gpa_signals()
  │    └─ 提取: GPA数值 / 985|211 / 学历层次 / 排名要求
  │
  └─ [LLM] 正则结果 + 完整 JD → GPACheckData
       └─ 补全: 隐性要求 / 结构化显性要求 / overall_strictness
```

## 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `jd_text` | str | 原始 JD 全文 |
| `channel` | str | 来自 JDContext.channel，必须为 "campus" |

## 输出（GPACheckData）

| 字段 | 类型 | 说明 |
|------|------|------|
| `requirements` | list[EducationRequirement] | 所有要求条目 |
| `has_gpa_requirement` | bool | 是否含明确 GPA 要求 |
| `has_school_tier_requirement` | bool | 是否含 985/211/双一流 要求 |
| `min_degree` | str \| None | 最低学历 |
| `overall_strictness` | int (1–5) | 门槛严格程度 |
| `notes` | str | 补充说明 |

## 使用示例

```python
ctx = JDContext(
    request_id="req-001",
    user_id="u001",
    jd_text="校招招聘，要求985/211毕业，GPA≥3.5/5.0...",
    classification=JDClassification(channel="campus", ...),
)
output = await skill.invoke(ctx)
print(output.data["has_gpa_requirement"])       # True
print(output.data["has_school_tier_requirement"])  # True
```
