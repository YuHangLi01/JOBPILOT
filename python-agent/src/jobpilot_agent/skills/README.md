# skills/ — Skill 层

## 架构概览

```
调用方（LangGraph graph / HTTP 请求）
         │
         ▼
  SkillDispatcher.dispatch(ctx)
         │  遍历 SkillRegistry.all()
         │  逐个调用 skill.should_invoke(ctx)  ← 纯函数，< 1ms
         │  对选中 Skill 做依赖拓扑排序
         │
         ├─→ [invoked_sorted]  按顺序 await skill.invoke(ctx)
         └─→ [skipped]         记录日志后忽略

SkillRegistry（单例）
  │  register(skill)      ← 模块 import 时触发自注册
  │  get(name)
  │  resolve_dependencies(names)  ← Kahn BFS 拓扑排序
  └─ reset()              ← 仅测试用

每个 Skill
  ├─ metadata: SkillMetadata   ← name / description / when_to_use / dependencies
  ├─ should_invoke(ctx) → bool ← 纯规则，不调 LLM
  ├─ invoke(ctx) → SkillOutput ← 主逻辑，捕获所有异常
  └─ to_langchain_tool()       ← 暴露给 LLM tool-calling
```

## 文件说明

| 文件 | 职责 |
|------|------|
| `errors.py` | `SkillError` 及 4 个子类（Timeout / Input / External / LLM） |
| `context.py` | `JDContext` — Skill 调用的统一上下文（只读） |
| `base.py` | `Skill` ABC、`SkillMetadata`、`SkillOutput`、`SkillExample` |
| `registry.py` | `SkillRegistry` 单例 + `register_all_skills()` 批量注册 |
| `dispatcher.py` | `SkillDispatcher` — 规则路由 + 依赖排序 + 串行执行 |
| `skill_template/` | 新 Skill 的参考模板（含可运行的 `TemplateSkill`） |

## 新增 Skill 步骤

### 1. 复制模板目录

```bash
cp -r src/jobpilot_agent/skills/skill_template \
      src/jobpilot_agent/skills/my_new_skill
```

### 2. 修改 `index.py`

```python
# src/jobpilot_agent/skills/my_new_skill/index.py

class MyNewSkill(Skill):
    metadata = SkillMetadata(
        name="my_new_skill",           # 全局唯一，小写下划线
        description="一句话说明功能",
        when_to_use="触发条件描述",
        when_not_to_use="反条件描述",
        dependencies=[],               # 依赖其他 Skill 的 name 列表
        tags=["llm"],
    )

    def should_invoke(self, ctx: JDContext) -> bool:
        # 纯规则！不调 LLM，不做 I/O
        return ctx.job_type == "tech"

    async def invoke(self, ctx: JDContext) -> SkillOutput:
        start = time.monotonic()
        try:
            # 实现业务逻辑
            return SkillOutput(
                skill_name=self.metadata.name,
                success=True,
                data={"result": "..."},
                latency_ms=self._measure_ms(start),
            )
        except Exception as exc:
            return SkillOutput.make_error(
                skill_name=self.metadata.name,
                error_code="SKILL_ERROR",
                message=str(exc),
                latency_ms=self._measure_ms(start),
            )

registry.register(MyNewSkill())   # 模块 import 时自动注册
```

### 3. 在 `registry.py` 启用 import

```python
# skills/registry.py: register_all_skills()
from jobpilot_agent.skills.my_new_skill import index as _my  # noqa: F401
```

### 4. 更新 SKILL.md

填写完整的 `when_to_use` / 输入输出 Schema / 示例。

### 5. 添加单元测试

```bash
# tests/skills/test_my_new_skill.py
```

至少覆盖：
- `should_invoke` 正反例各 1 个
- `invoke` 正常路径返回 `success=True`
- `invoke` 异常路径返回 `success=False`（不抛原生异常）

## 双接口使用示例

### LangGraph 业务层接口

```python
from jobpilot_agent.skills import SkillDispatcher, JDContext

dispatcher = SkillDispatcher()

# 路由决策
invoked, skipped = dispatcher.dispatch(ctx)
print("将调用:", [s.name for s in invoked])
print("将跳过:", [s.name for s in skipped])

# 路由 + 执行
outputs, skipped = await dispatcher.dispatch_and_run(ctx)
for out in outputs:
    if out.success:
        print(out.skill_name, out.data)
    else:
        print(f"[FAIL] {out.skill_name}: {out.error}")
```

### LangChain Tool-calling

```python
from jobpilot_agent.skills import registry

tools = [skill.to_langchain_tool() for skill in registry.all()]
# 传给 langchain_core / langgraph bind_tools
llm_with_tools = llm.bind_tools(tools)
```

## Skill 路由规则表

路由规则封装在各 Skill 的 `should_invoke()` 中：

| Skill | 触发条件 | 排除条件 |
|-------|----------|----------|
| `tech_stack_extract` | job_type=tech | — |
| `interview_rag` | 任意 job_type | — |
| `github_scan` | job_type=tech AND level in [senior, lead] | product / design / ops / mgmt |
| `portfolio_check` | job_type in [product, design] | github_scan 场景 |
| `gpa_check` | channel=campus | channel=social |
| `en_translate` | locale=en | locale=zh |

## 反模式警告

| 禁止 | 原因 |
|------|------|
| `should_invoke` 内调 LLM | 会让路由延迟从 < 1ms 升到 > 500ms |
| `invoke` 抛原生异常 | 调用方无法区分 Skill 失败与框架错误 |
| Registry 自动扫描目录 | 不可控，难以追踪哪些 Skill 被加载 |
| Dispatcher 内写业务规则 | 违反单一职责，规则应在各 Skill 的 `should_invoke` 里 |
| SKILL.md 不写结构化字段 | LLM tool-calling 描述质量下降，路由准确率降低 |

## 调试端点（开发用）

FastAPI 启动后可用：

```bash
# 列出所有注册 Skill
GET  http://localhost:8000/api/v1/skills

# 检查某 Skill 是否触发（给定 context）
POST http://localhost:8000/api/v1/skills/template_skill/dispatch-check
{
  "jd_text": "Python 后端工程师",
  "classification": {"job_type": "tech", "sub_type": "backend",
                     "level": "senior", "locale": "zh", "channel": "social"}
}

# 直接调用某 Skill
POST http://localhost:8000/api/v1/skills/template_skill/invoke
{
  "jd_text": "Python 后端工程师，5 年经验..."
}
```
