"""Evaluate prompt：对候选人回答进行多维度打分，以及整体报告生成。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jobpilot_agent.graphs.interview.state import InterviewStage


EVALUATE_SYSTEM = (
    "你是一位公正的面试评估专家。根据提供的问题、预期要点和候选人回答，"
    "对候选人进行多维度评分（0-10分）。\n"
    "\n评分维度：\n"
    "- clarity：表达清晰度\n"
    "- technical_depth：技术深度\n"
    "- relevance：回答相关性\n"
    "- problem_solving：问题解决能力\n"
    "- communication：沟通能力\n"
    "\n每个维度输出：score（0-10），evidence（从回答中节选 1-2 句支撑），"
    "improvement_hint（可选改进建议）。\n"
    "\n输出格式（JSON）：\n"
    "{\n"
    '  "signals": [\n'
    '    {"dimension": "clarity", "score": 8.5, "evidence": "...", "improvement_hint": null},\n'
    "    ...\n"
    "  ]\n"
    "}"
)


def build_evaluate_prompt(
    question: str,
    answer: str,
    stage: InterviewStage,
    answer_points: list[str],
) -> tuple[str, str]:
    points_text = "\n".join(f"- {p}" for p in answer_points) or "（无预期要点）"
    user = (
        f"面试阶段：{stage}\n"
        f"\n面试问题：\n{question}\n"
        f"\n预期回答要点：\n{points_text}\n"
        f"\n候选人实际回答：\n{answer}\n"
        "\n请对候选人回答进行多维度评分。"
    )
    return EVALUATE_SYSTEM, user


REPORT_SYSTEM = (
    "你是一位专业的面试评估专家，负责根据完整面试记录生成结构化复盘报告。\n"
    "报告要求：\n"
    "- stage_scores：各阶段得分（0-10），未进入的阶段得分设为 -1\n"
    "- highlights：3-5 条具体亮点，引用候选人实际表现\n"
    "- improvements：3-5 条可改进建议，给出具体方向\n"
    "- transcript_summary：100-200 字整体印象摘要\n"
    "\n输出格式（JSON）：\n"
    "{\n"
    '  "stage_scores": {"intro": 8.0, "project_deep_dive": 7.5, "tech_qa": 6.0, "scenario": 7.0, "reverse": 8.5},\n'
    '  "highlights": ["..."],\n'
    '  "improvements": ["..."],\n'
    '  "transcript_summary": "..."\n'
    "}\n\n"
    "示例（片段）：\n"
    '{"stage_scores": {"intro": 8.0, "project_deep_dive": 7.5, "tech_qa": 6.0, "scenario": 7.0, "reverse": 8.5},'
    ' "highlights": ["候选人在项目深挖阶段对 Redis 集群方案的阐述清晰且有数据支撑"],'
    ' "improvements": ["技术问答阶段对分布式一致性的理解偏浅，建议深入 Raft 协议"],'
    ' "transcript_summary": "候选人整体表现稳健，项目经验丰富，技术深度有待加强。"}'
)

REVERSE_ANSWER_SYSTEM = (
    "你是一位{company}的技术面试官，候选人向你提出了一个问题，请用专业、诚实的口吻回答。\n"
    "注意：\n"
    "  - 不要承诺具体薪资 / offer\n"
    "  - 语气真诚，符合{company}的技术文化定位\n"
    "  - 回答 100-200 字\n"
    '输出格式（JSON）：{{"content": "面试官的回答"}}'
)


def build_report_prompt(
    transcript_text: str,
    signals_summary: str,
    profile_summary: str,
) -> tuple[str, str]:
    """生成整体面试复盘报告的 prompt。"""
    user = (
        f"候选人档案摘要：\n{profile_summary}\n\n"
        f"各轮表现信号（各阶段均分）：\n{signals_summary}\n\n"
        f"面试记录（节选）：\n{transcript_text}\n\n"
        "请生成完整的面试复盘报告。"
    )
    return REPORT_SYSTEM, user


def build_reverse_answer_prompt(
    company: str,
    position: str,
    candidate_question: str,
) -> tuple[str, str]:
    """面试官回答候选人反问的 prompt。"""
    system = REVERSE_ANSWER_SYSTEM.format(company=company)
    user = (
        f"应聘职位：{position}\n"
        f"候选人的问题：{candidate_question}\n\n"
        "请以面试官身份回答。"
    )
    return system, user


def build_closing_prompt(company: str, position: str) -> tuple[str, str]:
    """生成面试结束语的 prompt。"""
    system = (
        "你是一位面试官，面试刚刚结束。请给出一段礼貌、专业、中性的结束语。\n"
        "要求：不承诺结果，感谢候选人时间，说明后续流程。\n"
        '输出格式（JSON）：{"content": "结束语正文"}'
    )
    user = f"应聘公司：{company}\n应聘职位：{position}\n请生成面试结束语。"
    return system, user


def build_judge_continue_prompt(
    stage: InterviewStage,
    stage_round: int,
    transcript_summary: str,
) -> tuple[str, str]:
    system = (
        "你是一位面试官，需要判断当前阶段是否应该继续追问。\n"
        "若候选人已充分展示了该阶段应有的能力，则停止；否则继续追问。\n"
        '输出格式（JSON）：{"should_continue": true/false, "reason": "一句话理由"}'
    )
    user = (
        f"当前阶段：{stage}，已进行 {stage_round} 轮\n"
        f"\n对话摘要：\n{transcript_summary}\n"
        "\n是否应该继续在本阶段追问？"
    )
    return system, user
