"""候选人档案构建器——从 user_kb RAG 检索并聚合成结构化档案。"""

from __future__ import annotations

from jobpilot_agent.graphs.interview.state import CandidateProfile
from jobpilot_agent.integrations.llm_client import get_llm_client
from jobpilot_agent.logging_setup import get_logger
from jobpilot_agent.retrieval import search_user_kb

log = get_logger(__name__)

PROFILE_SYSTEM_PROMPT = (
    "你是一位资深 HR，擅长从简历文本中提取结构化信息。\n"
    "请从以下简历/作品集文本中，提取候选人档案，输出 JSON：\n"
    "{\n"
    '  "user_id": "（从输入中取，无则留空字符串）",\n'
    '  "resume_summary": "100 字以内的整体摘要",\n'
    '  "top_projects": ["亮点项目 1（一句话描述）", "亮点项目 2", ...],\n'
    '  "tech_strengths": ["技术强项 1", "技术强项 2", ...],\n'
    '  "potential_weaknesses": ["可能被挑战的短板 1", ...]\n'
    "}\n"
    "要求：\n"
    "- resume_summary ≤ 100 字\n"
    "- top_projects 至多 5 条，每条一句话\n"
    "- tech_strengths / potential_weaknesses 各至多 5 条\n"
    "- 若文本不足以判断，对应字段输出空列表"
)


async def build_candidate_profile(
    user_id: str,
    jd_context: dict[str, object] | None = None,
) -> CandidateProfile:
    """从 user_kb 检索简历内容并构建结构化候选人档案。

    Args:
        user_id: 用户 ID（多租户隔离键）。
        jd_context: 可选，来自 JD 路由主图的上下文（含 jd_text），提升检索相关性。

    Returns:
        CandidateProfile，user_kb 为空时返回占位档案。
    """
    query = ""
    if jd_context:
        query = str(jd_context.get("jd_text", ""))

    try:
        docs = await search_user_kb(query=query or user_id, top_k=8, user_id=user_id)
    except Exception as e:
        log.warning("profile_builder.search_failed", user_id=user_id, error=str(e))
        docs = []

    if not docs:
        log.info("profile_builder.empty_kb", user_id=user_id)
        return CandidateProfile(
            user_id=user_id,
            resume_summary="（候选人未提供简历信息）",
        )

    text = "\n\n".join(d.text for d in docs)
    llm = get_llm_client()
    result, usage = await llm.chat_json(
        system=PROFILE_SYSTEM_PROMPT,
        user=f"user_id: {user_id}\n\n简历文本：\n{text}",
        schema=CandidateProfile,
        temperature=0.0,
    )
    assert isinstance(result, CandidateProfile)
    result.user_id = user_id  # 确保 user_id 正确
    log.info(
        "profile_builder.built",
        user_id=user_id,
        tokens=usage.total_tokens,
        projects=len(result.top_projects),
    )
    return result
