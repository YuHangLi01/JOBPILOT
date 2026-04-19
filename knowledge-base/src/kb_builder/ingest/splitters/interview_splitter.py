"""面经切片器：每个 turn 作为一个独立 chunk。

在 metadata 中保留 `prev_turn_text` / `next_turn_text`，方便 Replay 评估时
回退上下文。边界（第一 / 最后一轮）对应字段留空串。
"""

from __future__ import annotations

from kb_builder.models import InterviewChunk, StructuredInterview


def split_interview(interview: StructuredInterview) -> list[InterviewChunk]:
    chunks: list[InterviewChunk] = []

    turns = interview.turns
    for i, turn in enumerate(turns):
        content = (turn.content or "").strip()
        if not content:
            continue

        prev_text = turns[i - 1].content.strip() if i - 1 >= 0 else ""
        next_text = turns[i + 1].content.strip() if i + 1 < len(turns) else ""

        chunks.append(
            InterviewChunk(
                doc_id=f"int-{interview.interview_id}-{turn.turn_id}",
                text=content,
                source_id=interview.interview_id,
                chunk_index=turn.turn_id,
                company=interview.company or "",
                position=interview.position or "",
                role=turn.role,
                stage=turn.stage or "unknown",
                level=interview.level,
                year=interview.year,
                outcome=interview.outcome or "unknown",
                prev_turn_text=prev_text,
                next_turn_text=next_text,
            )
        )

    return chunks
