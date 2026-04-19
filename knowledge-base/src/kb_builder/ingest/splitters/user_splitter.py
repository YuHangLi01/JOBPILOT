"""用户简历切片器。

约定：用户上传的简历为 Markdown，一级标题 `#` 是文件名/姓名不关心，
二级标题 `##` 是章节（教育 / 工作 / 项目 / 技能 / 基本信息），三级标题 `###`
是该章节下的子条目（公司、项目名）。按 H2 / H3 切。
"""

from __future__ import annotations

from pathlib import Path

from langchain_text_splitters import MarkdownHeaderTextSplitter

from kb_builder.models import UserChunk, UserSection

_SPLITTER = MarkdownHeaderTextSplitter(
    headers_to_split_on=[("##", "section_title"), ("###", "subsection_title")],
)

_SECTION_ALIASES: dict[str, UserSection] = {
    "基本信息": "basic",
    "个人信息": "basic",
    "基础信息": "basic",
    "教育经历": "education",
    "教育背景": "education",
    "education": "education",
    "工作经历": "work_experience",
    "工作经验": "work_experience",
    "职业经历": "work_experience",
    "experience": "work_experience",
    "项目经验": "projects",
    "项目经历": "projects",
    "projects": "projects",
    "技能": "skills",
    "技术栈": "skills",
    "专业技能": "skills",
    "skills": "skills",
}


def _canonical_section(section_title: str) -> UserSection:
    title_lc = section_title.strip().lower()
    for key, canonical in _SECTION_ALIASES.items():
        if key.lower() in title_lc:
            return canonical
    return "other"


def split_user_doc(path: str | Path, user_id: str) -> list[UserChunk]:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")

    parts = _SPLITTER.split_text(raw)

    chunks: list[UserChunk] = []
    for idx, doc in enumerate(parts):
        body = (doc.page_content or "").strip()
        metadata = doc.metadata or {}
        section_title = metadata.get("section_title", "") or metadata.get("subsection_title", "")
        if not body:
            continue

        # H3 下 section 复用上级 H2 语义
        section_key = metadata.get("section_title") or metadata.get("subsection_title") or ""
        canonical = _canonical_section(section_key)

        sub_title = metadata.get("subsection_title") or section_title or "untitled"

        chunks.append(
            UserChunk(
                doc_id=f"usr-{user_id}-{idx}",
                text=body,
                source_id=user_id,
                chunk_index=idx,
                user_id=user_id,
                doc_type="resume",
                section=canonical,
                section_title=sub_title,
            )
        )

    return chunks
