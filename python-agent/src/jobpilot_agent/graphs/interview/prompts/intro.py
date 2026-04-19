"""Intro 阶段 prompt：轻松暖场，引导自我介绍。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jobpilot_agent.graphs.interview.interviewer_core import InterviewerInput
    from jobpilot_agent.retrieval import RetrievalResult


def build_prompt(
    input: InterviewerInput,
    rag_docs: list[RetrievalResult],
    top_k: int | None = None,
) -> tuple[str, str]:
    rag_text = _format_rag(rag_docs)
    profile_text = _format_profile(input)
    if top_k:
        fmt_instruction = (
            f"输出格式（JSON，生成 {top_k} 个候选问题）：\n"
            '{{"questions": [{{"content": "问题正文", "intent": "出题意图", "answer_points": ["要点"], "alternatives": []}}, ...]}}'
        )
        user_suffix = f"请生成 {top_k} 个适合 intro 阶段的开场候选问题（多样性优先）。"
    else:
        fmt_instruction = (
            "输出格式（JSON）：\n"
            '{{"content": "问题正文", "intent": "出题意图（1 句话）", "answer_points": ["预期回答要点 1", "预期回答要点 2"], "alternatives": []}}'
        )
        user_suffix = "请生成一个适合 intro 阶段的开场问题。"

    system = (
        "你是一位专业但亲切的技术面试官，正在进行面试的开场阶段（intro）。\n"
        "目标：让候选人放松，引导其做简短自我介绍，并从简历亮点中挑 1 个点追问。\n"
        "语气：友好、专业，避免刁难性问法。\n"
        f"{fmt_instruction}\n\n"
        "示例：\n"
        "场景：候选人应聘字节跳动后端工程师，简历上有 ByteKV 分布式缓存项目\n"
        '输出：{"content": "你好！先简单介绍一下自己吧，聊聊你最近在做什么、为什么对这个岗位感兴趣。",'
        ' "intent": "让候选人放松并建立基本印象", "answer_points": ["当前背景/经历", "对该岗位兴趣点"], "alternatives": []}'
    )

    user = (
        f"应聘公司：{input.company}\n"
        f"应聘职位：{input.position}\n"
        f"\n候选人档案摘要：\n{profile_text}\n"
        f"\n参考真实面经（RAG）：\n{rag_text}\n"
        f"\n{user_suffix}"
    )
    return system, user


def _format_rag(docs: list[RetrievalResult]) -> str:
    if not docs:
        return "（无相关面经）"
    return "\n".join(f"- {d.text[:200]}" for d in docs[:3])


def _format_profile(input: InterviewerInput) -> str:
    if not input.candidate_profile:
        return "（未提供候选人档案）"
    p = input.candidate_profile
    return (
        f"简历摘要：{p.resume_summary}\n"
        f"亮点项目：{', '.join(p.top_projects[:3]) or '无'}\n"
        f"技术优势：{', '.join(p.tech_strengths[:3]) or '无'}"
    )
