"""github_scan Skill 输出 Schema。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class GitHubRepo(BaseModel):
    """单个 GitHub 仓库信息。

    Attributes:
        name: 仓库名称。
        description: 仓库描述。
        stars: Star 数量。
        primary_language: 主要编程语言。
        recent_activity: 近 6 个月是否有 commit。
        url: 仓库 URL。
        readme_summary: README 摘要（LLM 生成，最多 100 字）。
    """

    name: str
    description: Optional[str] = None
    stars: int = 0
    primary_language: Optional[str] = None
    recent_activity: bool = False
    url: str
    readme_summary: Optional[str] = None


class GitHubScanData(BaseModel):
    """github_scan Skill 完整输出。

    Attributes:
        username: GitHub 用户名。
        public_repo_count: 公开仓库总数。
        total_stars: 所有仓库 star 总数。
        top_repos: 最多 3 个高质量代表仓库。
        language_distribution: 各语言占比（%，按代码行数加权）。
        matched_stack: 命中 JD 技术栈要求的技术列表。
        missing_stack: JD 要求但 GitHub 没有体现的技术列表。
        standout_projects: 可写进简历的 2–3 个亮点项目名。
        interview_talking_points: 面试可谈的角度（3–5 条）。
    """

    username: str
    public_repo_count: int = 0
    total_stars: int = 0

    top_repos: list[GitHubRepo] = Field(
        default_factory=list,
        description="最多 3 个代表仓库，按 star 数降序",
    )
    language_distribution: dict[str, float] = Field(
        default_factory=dict,
        description="各语言代码占比（%，总和约为 100），如 {'Python': 65.2, 'TypeScript': 25.1}",
    )

    matched_stack: list[str] = Field(
        default_factory=list,
        description="GitHub 已体现、且 JD 也要求的技术列表",
    )
    missing_stack: list[str] = Field(
        default_factory=list,
        description="JD 要求但 GitHub 未体现的技术列表",
    )
    standout_projects: list[str] = Field(
        default_factory=list,
        description="建议写进简历的 2–3 个亮点项目名（具体可谈）",
    )
    interview_talking_points: list[str] = Field(
        default_factory=list,
        description="面试可重点展示的角度，3–5 条，每条可直接准备回答",
    )
