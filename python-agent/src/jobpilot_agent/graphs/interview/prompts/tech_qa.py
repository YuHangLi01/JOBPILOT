"""Tech QA 阶段 prompt：技术问答，随轮次递进难度。"""

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
    difficulty = _difficulty_hint(input.stage_round)
    if top_k:
        fmt_instruction = (
            f"输出格式（JSON，生成 {top_k} 个候选问题）：\n"
            '{{"questions": [{{"content": "问题正文", "intent": "出题意图", "answer_points": ["要点"], "alternatives": []}}, ...]}}'
        )
        user_suffix = f"请生成 {top_k} 道不同的 tech_qa 阶段技术题（多样性优先）。"
    else:
        fmt_instruction = (
            "输出格式（JSON）：\n"
            '{{"content": "问题正文", "intent": "出题意图", "answer_points": ["预期要点"], "alternatives": []}}'
        )
        user_suffix = "请生成一道 tech_qa 阶段的技术题。"

    system = (
        "你是一位技术面试官，正在进行技术问答阶段（tech_qa）。\n"
        f"当前难度档位：{difficulty}\n"
        "策略：\n"
        "  - 初级阶段：基础知识确认（数据结构、语言特性）\n"
        "  - 中级阶段：系统设计基础、STAR 追问\n"
        "  - 高级阶段：大规模系统设计、性能优化、分布式问题\n"
        "注意：避免与 project_deep_dive 阶段重复的问题；按 round 递进难度。\n"
        f"{fmt_instruction}\n\n"
        "示例 1（初级）：\n"
        '输出：{"content": "解释一下 HashMap 和 TreeMap 的区别，什么场景下会选择 TreeMap？",'
        ' "intent": "考察基础数据结构选型", "answer_points": ["哈希 vs 红黑树的时间复杂度", "有序遍历场景"], "alternatives": []}\n\n'
        "示例 2（高级）：\n"
        '输出：{"content": "如果让你设计一个支持 10 亿用户的消息推送系统，如何保证消息可靠投递和低延迟？",'
        ' "intent": "考察大规模分布式系统设计能力", "answer_points": ["消息队列选型", "推/拉模型", "幂等性保障", "降级策略"], "alternatives": []}'
    )

    user = (
        f"应聘公司：{input.company}\n"
        f"应聘职位：{input.position}\n"
        f"当前轮次：{input.stage_round + 1}（{difficulty}）\n"
        f"\n参考面经：\n{rag_text}\n"
        f"\n{user_suffix}"
    )
    return system, user


def _difficulty_hint(stage_round: int) -> str:
    if stage_round == 0:
        return "初级（基础概念）"
    elif stage_round <= 2:
        return "中级（STAR 追问 + 原理）"
    else:
        return "高级（系统设计 / 大规模场景）"
