# contracts/

此目录为 JobPilot 双栈架构的 **API 契约源头**。

## 重要规则

> **禁止手工修改此目录下的任何文件。**

所有文件均由 Python Agent 侧自动生成，手工修改会在下次同步时被覆盖，且会导致 CI 检查失败。

## 文件说明

| 文件 | 说明 |
|------|------|
| `openapi.json` | 由 FastAPI 自动生成的 OpenAPI 3.1.0 规范，是两端类型同步的唯一真相源 |

## 更新流程

当 Python Agent 的 Pydantic Schema 发生变化时：

```bash
# 在项目根目录执行
make contracts
```

这条命令会：
1. 重新从 FastAPI 导出最新 `openapi.json`
2. 在 Node.js 侧重新生成 `src/integrations/python-agent/generated.ts`

然后将所有变更（包括本目录和 `generated.ts`）一起提交。

## CI 检查

每次 PR 和 push 到 main 分支时，GitHub Actions 会自动验证：
- `openapi.json` 与当前 Python Schema 一致
- `generated.ts` 与当前 `openapi.json` 一致

若任一检查失败，请本地运行 `make contracts` 后重新提交。
