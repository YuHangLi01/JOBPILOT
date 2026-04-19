"""Reverse 阶段 prompt：候选人反问问题收尾。"""

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
    if top_k:
        fmt_instruction = (
            f"输出格式（JSON，生成 {top_k} 个候选反问）：\n"
            '{{"questions": [{{"content": "反问问题正文", "intent": "目的", "answer_points": ["面试官可能如何回答"], "alternatives": []}}, ...]}}'
        )
        user_suffix = f"请生成 {top_k} 个候选人可以在 reverse 阶段向面试官提出的好问题（多样性优先）。"
    else:
        fmt_instruction = (
            "输出格式（JSON）：\n"
            '{{"content": "反问问题正文", "intent": "问这个问题的目的", "answer_points": ["面试官可能如何回答"], "alternatives": []}}'
        )
        user_suffix = "请生成一个候选人可以在 reverse 阶段向面试官提出的好问题。"

    system = (
        "你是一位面试官，现在进入了反问阶段（reverse）。\n"
        "角色转换：你现在要生成候选人「可以问面试官」的高质量问题。\n"
        "这些问题应该：\n"
        "  - 显示候选人对公司的深度研究\n"
        "  - 探索团队文化、技术栈或职业发展\n"
        "  - 不涉及薪资福利（那是 HR 环节）\n"
        f"{fmt_instruction}\n\n"
        "示例：\n"
        "场景：应聘字节跳动后端工程师\n"
        '输出：{"content": "请问团队现在最大的技术挑战是什么？加入后我可以从哪里开始贡献价值？",'
        ' "intent": "了解团队现状并展示主动性",'
        ' "answer_points": ["当前技术瓶颈", "新人上手路径"], "alternatives": []}'
    )

    user = (
        f"应聘公司：{input.company}\n"
        f"应聘职位：{input.position}\n"
        f"\n{user_suffix}"
    )
    return system, user
