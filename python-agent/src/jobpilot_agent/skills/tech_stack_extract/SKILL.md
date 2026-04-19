# tech_stack_extract

```yaml
name: tech_stack_extract
version: 0.1.0
tags: [llm, tech_stack, jd_analysis]
dependencies: []
```

## 功能描述

从职位描述（JD）文本中自动提取完整技术栈，包括：

- 编程语言（language）
- 框架与库（framework）
- 数据库（database）
- DevOps 与运维工具（devops）
- 云平台（cloud）
- 其他工具（tool / other）

每个技术项包含：名称、分类、是否必需、要求年限（可选）、原文引用。

## 触发条件（should_invoke）

```
job_type NOT IN {ops, mgmt, hr, finance, legal}
AND len(jd_text) >= 200
```

## 不触发条件

- 运营（ops）、管理（mgmt）、HR、财务、法务等非技术岗位
- JD 文本过短（< 200 字），内容不足以提取有效技术信息

## 输入

| 字段 | 类型 | 说明 |
|------|------|------|
| `jd_text` | str | 原始 JD 全文（来自 JDContext） |

## 输出（TechStackExtractData）

| 字段 | 类型 | 说明 |
|------|------|------|
| `tech_stack` | list[TechSkillItem] | 技术技能列表，required=True 排前面 |
| `primary_language` | str \| None | 主编程语言，无法判断时为 null |
| `tech_complexity` | int (1–5) | 技术栈复杂度评分 |
| `summary` | str | 一句话中文总结（≤ 50 字） |

### TechSkillItem 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 技术名称 |
| `category` | str | 分类：language/framework/database/devops/cloud/tool/other |
| `required` | bool | 是否为硬性要求 |
| `experience_years` | int \| None | 明确要求年限，无时为 null |
| `evidence_quote` | str | 来自 JD 原文的直接引用（≤ 60 字） |

## Prompt 策略

- System prompt：内嵌 JSON schema 约束，明确 evidence_quote 规则
- User prompt：2 个 few-shot 示例（前端 + 算法），再拼入实际 JD
- temperature=0.0：保证输出稳定可重复

## 使用示例

```python
from jobpilot_agent.skills.context import JDContext
from jobpilot_agent.skills.registry import registry

skill = registry.get("tech_stack_extract")
ctx = JDContext(
    request_id="req-001",
    user_id="u001",
    jd_text="Python 后端工程师，熟练掌握 Django、PostgreSQL...",
)
output = await skill.invoke(ctx)
print(output.data["primary_language"])   # "Python"
print(output.data["tech_complexity"])    # 3
```
