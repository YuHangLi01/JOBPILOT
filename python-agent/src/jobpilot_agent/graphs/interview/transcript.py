"""Transcript 工具函数（纯函数，无副作用）。"""

from __future__ import annotations

from jobpilot_agent.graphs.interview.state import InterviewStage, Turn


def format_transcript_for_llm(
    transcript: list[Turn],
    last_n: int = 20,
    include_stage_markers: bool = True,
) -> str:
    """将 transcript 格式化为 LLM 可消费的字符串。

    示例输出：
        ---[intro]---
        面试官: 先做个自我介绍吧
        候选人: 我叫...
        ---[project_deep_dive]---
        面试官: 你最有挑战的项目是？
    """
    role_label = {"interviewer": "面试官", "candidate": "候选人", "system": "系统"}
    recent = transcript[-last_n:] if len(transcript) > last_n else transcript

    lines: list[str] = []
    current_stage: str | None = None
    for turn in recent:
        if include_stage_markers and turn.stage != current_stage:
            current_stage = turn.stage
            lines.append(f"---[{current_stage}]---")
        label = role_label.get(turn.role, turn.role)
        lines.append(f"{label}: {turn.content}")

    return "\n".join(lines)


def get_last_candidate_turn(transcript: list[Turn]) -> Turn | None:
    """返回最后一条候选人发言（供评分节点使用）。"""
    for turn in reversed(transcript):
        if turn.role == "candidate":
            return turn
    return None


def count_stage_turns(transcript: list[Turn], stage: InterviewStage) -> int:
    """统计某阶段的发言总轮数。"""
    return sum(1 for t in transcript if t.stage == stage)


def next_turn_id(transcript: list[Turn]) -> int:
    """计算下一个 turn_id（空列表时从 1 开始）。"""
    if not transcript:
        return 1
    return max(t.turn_id for t in transcript) + 1
