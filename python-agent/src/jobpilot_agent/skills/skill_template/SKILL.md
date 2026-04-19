---
name: template_skill
version: 0.1.0
description: "示例 Skill，演示 Skill 开发规范，不产生实际业务效果"
tags: []
dependencies: []
---

# Template Skill

## 用途

这是一个开发模板，供创建新 Skill 时复制参考。
实际 Skill 在此描述其解决的具体业务问题与场景。

## 何时使用（When to Use）

- 场景 1：满足触发条件 A 时（例如 job_type == "tech"）
- 场景 2：满足触发条件 B 时（例如 locale == "en"）

## 何时不用（When NOT to Use）

- 反条件 1：job_type 不在目标范围时（如纯运营岗）
- 反条件 2：classification 为 None 时（分类节点尚未完成）

## 输入 Schema

```json
{
  "jd_text": "string（JD 原文）",
  "user_context": {
    "preferred_lang": "zh | en",
    "user_kb_id": "string | null"
  }
}
```

## 输出 Schema

```json
{
  "skill_name": "template_skill",
  "success": true,
  "data": {
    "field_a": "string",
    "field_b": ["item1", "item2"]
  },
  "latency_ms": 42,
  "tokens_used": 0,
  "llm_calls": 0,
  "external_calls": 0
}
```

## 示例

### 正例

- **场景**：技术岗 JD，need 提取技术栈
- **关键 context 字段**：`job_type="tech"`, `level="senior"`
- **期望输出**：`data.field_a = "技术栈列表"`

### 反例

- **场景**：产品岗 JD
- **为什么不应调用**：template_skill 仅面向技术岗，should_invoke 会返回 False

## 依赖

- 无外部依赖
- 故障回退：无需回退（本模板不调用外部服务）

## 开发清单（复制此模板时请逐项实现）

- [ ] 修改 `metadata.name`（全局唯一，小写下划线）
- [ ] 更新 `metadata.description` / `when_to_use` / `when_not_to_use`
- [ ] 实现 `should_invoke`（纯函数，不调 LLM）
- [ ] 实现 `async invoke`（捕获所有异常，填充度量字段）
- [ ] 更新本 SKILL.md 的示例与 Schema
- [ ] 在 `registry.py` 的 `register_all_skills()` 中加 import
- [ ] 添加单元测试到 `tests/skills/test_{skill_name}.py`
