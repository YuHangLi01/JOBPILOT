"""Replay pair 采样策略。"""

from __future__ import annotations

import random
from collections import defaultdict

from jobpilot_agent.evaluation.replay.schema import ReplayPair
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


def extract_replay_pairs(
    interviews: list[dict[str, object]],
    min_history_turns: int = 2,
    max_pairs_per_interview: int = 5,
) -> list[ReplayPair]:
    """从每条面经抽取可评估的「历史 → 真实追问」对。

    规则：
    - 遍历每对相邻 (candidate_turn, interviewer_turn) 切换点
    - 前缀历史至少 min_history_turns 个 turn
    - 每条面经最多 max_pairs_per_interview 对
    """
    all_pairs: list[ReplayPair] = []

    for interview in interviews:
        interview_id = str(interview.get("interview_id") or "")
        company = str(interview.get("company") or "unknown")
        position = str(interview.get("position") or "unknown")
        turns: list[dict[str, object]] = interview.get("turns") or []  # type: ignore[assignment]

        if len(turns) < 3:
            continue

        pairs_this_interview: list[ReplayPair] = []

        for i in range(len(turns) - 1):
            current = turns[i]
            next_turn = turns[i + 1]

            # 找「候选人 → 面试官」切换点
            if current.get("role") != "candidate":
                continue
            if next_turn.get("role") != "interviewer":
                continue

            history = turns[: i + 1]
            if len(history) < min_history_turns:
                continue

            # stage 取下一个面试官问题的 stage
            stage = str(next_turn.get("stage") or current.get("stage") or "unknown")

            history_text = _format_history(history)

            pair = ReplayPair(
                interview_id=interview_id,
                pair_id=f"{interview_id}-{next_turn.get('turn_id', i + 1)}",
                company=company,
                position=position,
                stage=stage,
                history_turns_raw=history,
                history_text=history_text,
                real_next_question=str(next_turn.get("content", "")),
                real_next_intent=None,
            )
            pairs_this_interview.append(pair)

            if len(pairs_this_interview) >= max_pairs_per_interview:
                break

        all_pairs.extend(pairs_this_interview)

    log.info(
        "extract_replay_pairs.done",
        interviews=len(interviews),
        pairs=len(all_pairs),
    )
    return all_pairs


def stratified_sample(
    pairs: list[ReplayPair],
    target_count: int = 500,
    by: str = "stage",
    seed: int = 42,
) -> list[ReplayPair]:
    """按指定字段分层抽样至 target_count。

    每层按比例抽样，保证各层均有代表。
    """
    if len(pairs) <= target_count:
        log.info("stratified_sample.no_op", pairs=len(pairs), target=target_count)
        return pairs

    rng = random.Random(seed)

    # 分组
    groups: dict[str, list[ReplayPair]] = defaultdict(list)
    for p in pairs:
        key = getattr(p, by, "unknown")
        groups[str(key)].append(p)

    # 按比例分配名额
    sampled: list[ReplayPair] = []
    total = len(pairs)
    remaining = target_count

    sorted_keys = sorted(groups.keys())
    for idx, key in enumerate(sorted_keys):
        group = groups[key]
        # 最后一组补齐剩余
        if idx == len(sorted_keys) - 1:
            quota = remaining
        else:
            quota = round(len(group) / total * target_count)
            quota = min(quota, len(group))
            remaining -= quota

        sampled_group = rng.sample(group, min(quota, len(group)))
        sampled.extend(sampled_group)

    rng.shuffle(sampled)
    log.info(
        "stratified_sample.done",
        original=len(pairs),
        sampled=len(sampled),
        groups=len(groups),
    )
    return sampled


def _format_history(turns: list[dict[str, object]]) -> str:
    """将历史 turn 格式化为可读字符串。"""
    lines = []
    for t in turns:
        role = t.get("role", "?")
        content = t.get("content", "")
        prefix = "面试官" if role == "interviewer" else "候选人"
        lines.append(f"[{prefix}] {content}")
    return "\n".join(lines)
