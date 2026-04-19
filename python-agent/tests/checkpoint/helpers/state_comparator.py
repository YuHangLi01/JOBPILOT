"""状态一致性比对器。"""

from __future__ import annotations

from typing import Any

STRICT_FIELDS = [
    "current_stage",
    "transcript",
    "performance_signals",
    "stage_round_count",
    "stage_history",
    "candidate_profile",
    "company",
    "position",
]


class StateInconsistency(Exception):
    """状态一致性校验失败。"""


def assert_states_equal(
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    strict_fields: list[str] | None = None,
) -> None:
    """断言 kill 前/重启后的状态完全一致。

    只比对 strict_fields 中的字段；其他字段（errors/metadata 等）允许差异。
    """
    fields = strict_fields if strict_fields is not None else STRICT_FIELDS
    v1: dict[str, Any] = state_before.get("values", {})
    v2: dict[str, Any] = state_after.get("values", {})

    discrepancies: list[dict[str, Any]] = []
    for field in fields:
        a = v1.get(field)
        b = v2.get(field)
        if not _deep_equal(a, b):
            discrepancies.append({"field": field, "before": a, "after": b})

    if discrepancies:
        detail = "\n".join(
            f"  - {d['field']}: before={d['before']!r}  after={d['after']!r}"
            for d in discrepancies
        )
        raise StateInconsistency(
            f"States differ in {len(discrepancies)} field(s):\n{detail}"
        )


def _deep_equal(a: Any, b: Any) -> bool:
    """深度比较，处理 list[Turn] / list[PerformanceSignal] / datetime str / dict / primitive。"""
    if type(a) is not type(b):
        # Allow None vs missing gracefully
        if a is None and b is None:
            return True
        return False

    if isinstance(a, list):
        if len(a) != len(b):
            return False
        # 尝试按 turn_id 排序（Turn 列表）
        try:
            a_sorted = sorted(a, key=lambda x: x.get("turn_id", 0) if isinstance(x, dict) else 0)
            b_sorted = sorted(b, key=lambda x: x.get("turn_id", 0) if isinstance(x, dict) else 0)
        except Exception:  # noqa: BLE001
            a_sorted, b_sorted = a, b
        return all(_deep_equal(x, y) for x, y in zip(a_sorted, b_sorted))

    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_deep_equal(a[k], b[k]) for k in a)

    # Primitive comparison (covers strings, ints, floats, bools, None)
    return a == b


def summarize_state(state: dict[str, Any]) -> dict[str, Any]:
    """提取关键字段摘要，用于日志打印。"""
    values: dict[str, Any] = state.get("values", {})
    transcript: list[Any] = values.get("transcript", [])
    signals: list[Any] = values.get("performance_signals", [])
    turn_ids = [
        t.get("turn_id", 0) for t in transcript if isinstance(t, dict)
    ]
    return {
        "current_stage": values.get("current_stage"),
        "transcript_count": len(transcript),
        "last_turn_id": max(turn_ids, default=0),
        "stage_round_count": values.get("stage_round_count"),
        "performance_signals_count": len(signals),
        "next_node": state.get("next"),
    }
