# github_scan

```yaml
name: github_scan
version: 0.1.0
tags: [external_api, llm]
dependencies: [tech_stack_extract]
```

## 功能描述

扫描候选人 GitHub 公开仓库，对照 JD 技术栈要求生成：

- 语言分布（按代码量加权占比）
- 命中 JD 的技术栈（`matched_stack`）
- JD 要求但 GitHub 未体现的技术（`missing_stack`）
- 2–3 个可写进简历的亮点项目
- 面试可谈的角度（3–5 条）

## 触发条件（should_invoke）

```
job_type == "tech"
AND level in {"senior", "lead"}
AND user_context.github_username 非空
```

## 不触发条件

- 非 tech 岗位（product/design/ops/mgmt）
- junior/middle 级别（经验不足以用 GitHub 评估）
- 无 `github_username`
- 绝不从 JD 文本正则抽取用户名（隐私合规）

## 执行流程

```
1. 速率限制检查（remaining ≤ buffer → SKILL_EXTERNAL_FAIL）
2. 并发：get_user + list_repos(per_page=30)
3. 筛选：非 fork + (star≥1 OR 近6月活跃) → top 10
4. 并发：get_repo_languages × N 仓库
5. 串行：get_readme × top-3 star 仓库
6. LLM 分析 → GitHubScanData
```

## 依赖说明

`dependencies: [tech_stack_extract]` 确保 `tech_stack_extract` 先执行，
`github_scan` 读取 `ctx.parsed_jd["tech_stack"]` 作为对照基准。
若 tech_stack 未提取，fallback 到 JD 原文让 LLM 推断。

## 配置

```env
GITHUB_TOKEN=ghp_xxx          # 可选，有则 5000/h，无则 60/h
GITHUB_RATE_LIMIT_BUFFER=5    # 剩余额度 ≤ 5 时拒绝新调用
```

## 错误处理

| 情况 | 返回 |
|------|------|
| 用户不存在（404） | `SKILL_INPUT_INVALID: GitHub user 'xxx' not found` |
| 速率限制耗尽 | `SKILL_EXTERNAL_FAIL: GitHub rate limit too low` |
| 其他 HTTP 错误 | `SKILL_EXTERNAL_FAIL: HTTP {status}: ...` |
| 整体超时 | `SKILL_TIMEOUT` |
