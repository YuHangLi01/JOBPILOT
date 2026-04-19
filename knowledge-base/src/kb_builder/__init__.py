"""JobPilot knowledge-base builder package.

将 P2.1 产出的 labeled JD / 结构化面经 / Markdown 简历切片并灌入
`jd_kb`、`interview_kb`、`user_kb` 三个 Milvus 集合。

对外 CLI 入口：`kb-ingest`（见 pyproject.toml `[project.scripts]`）。
"""

__version__ = "0.1.0"
