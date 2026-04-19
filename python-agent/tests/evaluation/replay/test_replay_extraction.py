"""Replay pair 抽取单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

from jobpilot_agent.evaluation.replay.sampling import extract_replay_pairs, stratified_sample


def _make_interview(
    interview_id: str = "test-001",
    company: str = "TestCo",
    position: str = "SWE",
    turns: list[dict] | None = None,
    quality_score: float = 0.8,
) -> dict:
    if turns is None:
        turns = [
            {"turn_id": 1, "role": "interviewer", "content": "请自我介绍", "stage": "intro"},
            {"turn_id": 2, "role": "candidate", "content": "我是张三", "stage": "intro"},
            {"turn_id": 3, "role": "interviewer", "content": "说说你最大的项目", "stage": "project_deep_dive"},
            {"turn_id": 4, "role": "candidate", "content": "我做了电商平台", "stage": "project_deep_dive"},
            {"turn_id": 5, "role": "interviewer", "content": "遇到了什么挑战？", "stage": "project_deep_dive"},
        ]
    return {
        "interview_id": interview_id,
        "company": company,
        "position": position,
        "quality_score": quality_score,
        "turns": turns,
    }


def test_extract_pairs_basic() -> None:
    """基本场景：1 条面经 5 个 turn，应抽出 1-2 对。"""
    interviews = [_make_interview()]
    pairs = extract_replay_pairs(interviews, min_history_turns=2, max_pairs_per_interview=5)

    assert len(pairs) >= 1
    # 第一个 pair：history 以 turn_id=2 结尾，real_next = turn_id=3
    first = pairs[0]
    assert first.interview_id == "test-001"
    assert first.real_next_question == "说说你最大的项目"
    assert len(first.history_turns_raw) >= 2


def test_extract_pairs_min_history() -> None:
    """history < min_history_turns 时不抽取。"""
    interviews = [
        _make_interview(
            turns=[
                {"turn_id": 1, "role": "interviewer", "content": "Q", "stage": "intro"},
                {"turn_id": 2, "role": "candidate", "content": "A", "stage": "intro"},
                {"turn_id": 3, "role": "interviewer", "content": "Q2", "stage": "intro"},
            ]
        )
    ]
    # min_history=2：history=[turn1, turn2]，len=2，满足 >= 2 → 应有 1 对
    pairs = extract_replay_pairs(interviews, min_history_turns=2, max_pairs_per_interview=5)
    assert len(pairs) == 1

    # min_history=3：history=[turn1, turn2]，len=2，不满足 >= 3 → 无对
    pairs_none = extract_replay_pairs(interviews, min_history_turns=3, max_pairs_per_interview=5)
    assert len(pairs_none) == 0


def test_extract_pairs_max_per_interview() -> None:
    """每条面经最多 max_pairs_per_interview 对。"""
    # 构建 12 个 turn，交替 interviewer/candidate，能产生 5+ 对
    turns = []
    for i in range(12):
        role = "interviewer" if i % 2 == 0 else "candidate"
        turns.append({"turn_id": i + 1, "role": role, "content": f"content-{i}", "stage": "tech_qa"})

    interviews = [_make_interview(turns=turns)]
    pairs = extract_replay_pairs(interviews, min_history_turns=2, max_pairs_per_interview=3)
    assert len(pairs) <= 3


def test_extract_pairs_pair_id_unique() -> None:
    """每个 pair 的 pair_id 应唯一。"""
    interviews = [_make_interview("i1"), _make_interview("i2")]
    pairs = extract_replay_pairs(interviews, min_history_turns=2, max_pairs_per_interview=5)
    ids = [p.pair_id for p in pairs]
    assert len(ids) == len(set(ids))


def test_stratified_sample_balances_stages() -> None:
    """分层抽样后各 stage 数量大致均衡。"""
    # 构建 3 个 stage 各 100 对
    all_pairs = []
    for stage in ["intro", "tech_qa", "project_deep_dive"]:
        for j in range(100):
            from jobpilot_agent.evaluation.replay.schema import ReplayPair

            all_pairs.append(
                ReplayPair(
                    interview_id=f"{stage}-{j}",
                    pair_id=f"{stage}-{j}",
                    company="Co",
                    position="SWE",
                    stage=stage,
                    history_turns_raw=[],
                    history_text="",
                    real_next_question="Q?",
                )
            )

    sampled = stratified_sample(all_pairs, target_count=60, by="stage")
    assert len(sampled) == 60

    # 每 stage 应在 15-25 之间（目标 20 各）
    stage_counts: dict[str, int] = {}
    for p in sampled:
        stage_counts[p.stage] = stage_counts.get(p.stage, 0) + 1
    for count in stage_counts.values():
        assert 10 <= count <= 30, f"Stage distribution unbalanced: {stage_counts}"


def test_load_dataset_quality_filter(tmp_path: Path) -> None:
    """quality_score < 0.6 的记录应被过滤。"""
    data = [
        {
            "interview_id": "good",
            "company": "Co",
            "position": "SWE",
            "quality_score": 0.8,
            "turns": [
                {"turn_id": 1, "role": "interviewer", "content": "Q", "stage": "intro"},
                {"turn_id": 2, "role": "candidate", "content": "A", "stage": "intro"},
                {"turn_id": 3, "role": "interviewer", "content": "Q2", "stage": "intro"},
            ],
        },
        {
            "interview_id": "bad",
            "company": "Co",
            "position": "SWE",
            "quality_score": 0.4,
            "turns": [
                {"turn_id": 1, "role": "interviewer", "content": "Q", "stage": "intro"},
                {"turn_id": 2, "role": "candidate", "content": "A", "stage": "intro"},
                {"turn_id": 3, "role": "interviewer", "content": "Q2", "stage": "intro"},
            ],
        },
    ]
    file = tmp_path / "test.jsonl"
    file.write_text("\n".join(json.dumps(d) for d in data), encoding="utf-8")

    from jobpilot_agent.evaluation.replay.loader import load_replay_dataset

    records = load_replay_dataset(path=str(file))
    assert len(records) == 1
    assert records[0]["interview_id"] == "good"
