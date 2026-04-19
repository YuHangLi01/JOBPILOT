"""Project deep dive 阶段 prompt：深挖亮点项目的技术细节与成果。"""

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
    rag_text = "\n".join(f"- {d.text[:200]}" for d in rag_docs[:3]) or "（无相关面经）"
    profile_text = _format_profile(input)
    round_hint = _round_hint(input.stage_round)
    if top_k:
        fmt_instruction = (
            f"输出格式（JSON，生成 {top_k} 个候选问题）：\n"
            '{{"questions": [{{"content": "问题正文", "intent": "出题意图", "answer_points": ["要点"], "alternatives": []}}, ...]}}'
        )
        user_suffix = f"请生成 {top_k} 道不同的本轮 project_deep_dive 候选问题（多样性优先）。"
    else:
        fmt_instruction = (
            "输出格式（JSON）：\n"
            '{{"content": "问题正文", "intent": "出题意图", "answer_points": ["预期要点"], "alternatives": []}}'
        )
        user_suffix = "请生成本轮 project_deep_dive 问题。"

    system = (
        "你是一位资深技术面试官，正在对候选人的项目经历进行深挖（project_deep_dive 阶段）。\n"
        "策略：\n"
        "  - 第 1 轮：请候选人介绍最有挑战的项目\n"
        "  - 第 2 轮：深挖技术选型理由或遇到的具体难点\n"
        "  - 第 3 轮以上：追问成果量化、复盘改进点\n"
        "注意：不要重复已经在 transcript 中问过的问题；每轮追问要比上一轮更深入。\n"
        "语气：专业、追问式，但不打断候选人思路。\n"
        f"{fmt_instruction}\n\n"
        "示例 1（第 1 轮）：\n"
        '输出：{"content": "能介绍一下你做过的最有技术挑战性的项目吗？重点聊聊背景、你的角色和遇到的核心难点。",'
        ' "intent": "了解候选人最硬核的项目经历", "answer_points": ["项目背景与规模", "候选人具体贡献", "核心技术难点"], "alternatives": []}\n\n'
        "示例 2（第 2 轮，候选人提到用了 Redis）：\n"
        '输出：{"content": "你提到用了 Redis 做缓存，为什么选 Redis 而不是 Memcached 或者本地缓存？在高并发下有没有遇到缓存击穿问题，怎么解决的？",'
        ' "intent": "考察技术选型深度及缓存实战经验", "answer_points": ["Redis vs 其他方案的权衡", "缓存击穿/穿透/雪崩的处理"], "alternatives": []}'
    )

    user = (
        f"应聘公司：{input.company}\n"
        f"应聘职位：{input.position}\n"
        f"当前轮次：第 {input.stage_round + 1} 轮（{round_hint}）\n"
        f"\n候选人档案：\n{profile_text}\n"
        f"\n参考面经：\n{rag_text}\n"
        f"\n{user_suffix}"
    )
    return system, user


def _round_hint(stage_round: int) -> str:
    hints = {0: "初次介绍项目", 1: "深挖技术细节", 2: "追问成果与复盘"}
    return hints.get(stage_round, "持续追问深度")


def _format_profile(input: InterviewerInput) -> str:
    if not input.candidate_profile:
        return "（未提供档案）"
    p = input.candidate_profile
    return (
        f"亮点项目：{', '.join(p.top_projects) or '无'}\n"
        f"技术强项：{', '.join(p.tech_strengths) or '无'}\n"
        f"潜在短板：{', '.join(p.potential_weaknesses) or '无'}"
    )
