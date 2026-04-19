"""Scenario 阶段 prompt：STAR 情境题，考察问题解决能力。"""

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
    if top_k:
        fmt_instruction = (
            f"输出格式（JSON，生成 {top_k} 个候选问题）：\n"
            '{{"questions": [{{"content": "情境题正文", "intent": "考察维度", "answer_points": ["评分点"], "alternatives": []}}, ...]}}'
        )
        user_suffix = f"请生成 {top_k} 道不同的情境题（多样性优先）。"
    else:
        fmt_instruction = (
            "输出格式（JSON）：\n"
            '{{"content": "情境题正文", "intent": "考察维度", "answer_points": ["关键评分点"], "alternatives": []}}'
        )
        user_suffix = "请生成一道贴合该职位的情境题。"

    system = (
        "你是一位面试官，正在进行情境题阶段（scenario）。\n"
        "目标：通过真实工作场景，考察候选人的 problem_solving 能力与决策思维。\n"
        "要求：\n"
        "  - 情境要具体（包含背景、约束、目标）\n"
        "  - 适合用 STAR 结构回答\n"
        "  - 不要有唯一「正确答案」\n"
        f"{fmt_instruction}\n\n"
        "示例：\n"
        "场景：应聘后端技术岗\n"
        '输出：{"content": "假设你负责的服务在大促前一天晚上突然出现 P99 延迟飙升，监控告警不断，你会怎么做？",'
        ' "intent": "考察候选人在压力下的问题排查与决策能力",'
        ' "answer_points": ["快速止血思路", "根因定位步骤", "沟通与升级判断", "事后复盘"], "alternatives": []}'
    )

    user = (
        f"应聘公司：{input.company}\n"
        f"应聘职位：{input.position}\n"
        f"\n参考面经：\n{rag_text}\n"
        f"\n{user_suffix}"
    )
    return system, user
