"""加载结构化面经数据集。"""

from __future__ import annotations

import json
from pathlib import Path

from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

# 相对 repo root：python-agent/src/jobpilot_agent/evaluation/replay/loader.py
# parents[0]=replay, [1]=evaluation, [2]=jobpilot_agent, [3]=src, [4]=python-agent, [5]=repo root
_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEFAULT_PATH = _REPO_ROOT / "knowledge-base/data/clean/interview_structured_filtered.jsonl"

_MIN_QUALITY_SCORE = 0.6


def load_replay_dataset(
    path: str | Path | None = None,
    min_quality_score: float = _MIN_QUALITY_SCORE,
) -> list[dict[str, object]]:
    """加载结构化面经，过滤低质量记录。

    Args:
        path: JSONL 文件路径。默认用 interview_structured_filtered.jsonl。
        min_quality_score: 低于此分值的记录被过滤。
    """
    file_path = Path(path) if path else _DEFAULT_PATH
    if not file_path.is_absolute():
        file_path = _REPO_ROOT / file_path

    if not file_path.exists():
        raise FileNotFoundError(f"Interview dataset not found: {file_path}")

    records: list[dict[str, object]] = []
    skipped_quality = 0
    skipped_malformed = 0

    with open(file_path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped_malformed += 1
                if skipped_malformed <= 3:
                    log.warning("loader.malformed_line", lineno=lineno)
                continue

            quality = rec.get("quality_score", 0.0) or 0.0
            if quality < min_quality_score:
                skipped_quality += 1
                continue

            # 必须有 turns 且至少 3 个（否则无法构建有效 pair）
            turns = rec.get("turns") or []
            if len(turns) < 3:
                skipped_quality += 1
                continue

            records.append(rec)

    log.info(
        "loader.done",
        loaded=len(records),
        skipped_quality=skipped_quality,
        skipped_malformed=skipped_malformed,
        path=str(file_path),
    )
    return records


def load_replay_pairs_from_jsonl(path: str | Path) -> list[object]:
    """从已保存的 pairs JSONL 文件加载。"""
    from jobpilot_agent.evaluation.replay.schema import ReplayPair

    pairs: list[object] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    pairs.append(ReplayPair.model_validate_json(line))
                except Exception:  # noqa: BLE001
                    pass
    return pairs


def load_replay_results_from_jsonl(path: str | Path) -> list[object]:
    """从已保存的 results JSONL 文件加载。"""
    from jobpilot_agent.evaluation.replay.schema import ReplayResult

    results: list[object] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(ReplayResult.model_validate_json(line))
                except Exception:  # noqa: BLE001
                    pass
    return results
