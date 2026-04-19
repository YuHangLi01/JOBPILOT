"""github_scan Skill 提示词模板。"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
你是一位技术招聘专家，擅长通过 GitHub 仓库分析候选人的技术能力，并对照 JD 要求给出匹配度分析。

## 任务
基于候选人 GitHub 数据和目标 JD，生成技术匹配度分析报告。

## 输出格式（严格 JSON）
{
  "username": "GitHub 用户名",
  "public_repo_count": 公开仓库数（整数）,
  "total_stars": 总 star 数（整数）,
  "top_repos": [
    {
      "name": "仓库名",
      "description": "仓库描述或 null",
      "stars": star 数,
      "primary_language": "主要语言或 null",
      "recent_activity": true|false（近 6 个月是否有 commit）,
      "url": "https://github.com/xxx/yyy",
      "readme_summary": "README 摘要（≤ 100 字，或 null）"
    }
  ],
  "language_distribution": {"Python": 65.2, "TypeScript": 25.1},
  "matched_stack": ["Python", "FastAPI", ...],
  "missing_stack": ["Kubernetes", ...],
  "standout_projects": ["项目A", "项目B"],
  "interview_talking_points": ["谈点1（具体）", "谈点2", ...]
}

## 关键规则
1. matched_stack / missing_stack 严格对照 JD 技术要求，不要包含 JD 没提到的技术
2. standout_projects 选 2–3 个最能展示 JD 所需技能的项目
3. interview_talking_points 每条具体可准备，如 "在 ProjectA 中用 Python 处理了 10M 级数据..."
4. readme_summary 来自 README 原文摘要，不得虚构
5. language_distribution 各语言占比之和约为 100（按代码量加权）
"""


def build_user_prompt(
    username: str,
    user_info: dict[str, Any],
    top_repos: list[dict[str, Any]],
    lang_distribution: dict[str, float],
    readmes: list[tuple[str, str | None]],
    jd_text: str,
    tech_stack: list[str],
) -> str:
    """构建包含 GitHub 数据和 JD 的 user prompt。

    Args:
        username: GitHub 用户名。
        user_info: GitHub 用户 API 返回数据。
        top_repos: 候选仓库列表（含元数据）。
        lang_distribution: 语言占比字典（%）。
        readmes: [(repo_name, readme_content)] 列表，readme 可为 None。
        jd_text: 原始 JD 文本。
        tech_stack: 已提取的 JD 技术栈列表（来自 tech_stack_extract 或 JD 原文）。

    Returns:
        完整 user prompt 字符串。
    """
    # 格式化 top repos
    repo_lines = []
    for repo in top_repos[:5]:
        repo_lines.append(
            f"- {repo['name']} (⭐{repo.get('stargazers_count', 0)}, "
            f"lang={repo.get('language', '?')}, "
            f"pushed={repo.get('pushed_at', '?')[:10]}): "
            f"{repo.get('description', '')}"
        )

    # 格式化 README
    readme_sections = []
    for repo_name, readme_content in readmes:
        if readme_content:
            # 截取前 500 字
            preview = readme_content[:500].replace("\n", " ").strip()
            readme_sections.append(f"[{repo_name}] {preview}")

    lang_str = ", ".join(f"{k}: {v:.1f}%" for k, v in sorted(lang_distribution.items(), key=lambda x: -x[1])[:8])

    return f"""## GitHub 用户数据
- 用户名：{username}
- 公开仓库数：{user_info.get("public_repos", "?")}
- 粉丝数：{user_info.get("followers", "?")}
- 简介：{user_info.get("bio", "（无）")}

## 主要仓库（按更新时间排序，非 fork）
{chr(10).join(repo_lines) if repo_lines else "（无）"}

## 语言分布（代码量占比）
{lang_str or "（无数据）"}

## 代表仓库 README 摘要
{chr(10).join(readme_sections) if readme_sections else "（无 README）"}

---

## 目标 JD（节选）
{jd_text[:2000]}

## JD 已提取技术栈
{", ".join(tech_stack) if tech_stack else "（未提取，请从 JD 文本推断）"}

---

请基于以上数据，生成技术匹配度分析 JSON。"""
