"""阶段推进准确率评估 Runner。"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from jobpilot_agent.evaluation.stage.metrics import StageEvalResult, compute_metrics
from jobpilot_agent.graphs.interview.interviewer_core import InterviewerCore
from jobpilot_agent.graphs.interview.state import InterviewStage, Turn
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

_MIN_TURNS = 5  # 面经 turns 至少这么多才抽样


def _rebuild_turn(raw: dict[str, Any]) -> Turn | None:
    """从面经原始 turn dict 重建 Turn 对象。"""
    try:
        stage = raw.get("stage") or "intro"
        return Turn(
            turn_id=int(raw.get("turn_id", 0)),
            role=raw["role"],
            content=str(raw.get("content", "")),
            stage=stage,  # type: ignore[arg-type]
        )
    except Exception:  # noqa: BLE001
        return None


class StagePredictor:
    """薄包装，便于测试 mock。"""

    def __init__(self, core: InterviewerCore) -> None:
        self.core = core

    async def predict(self, history: list[Turn]) -> InterviewStage:
        return await self.core.predict_stage(history)


class StageEvalSample:
    def __init__(
        self,
        interview_id: str,
        true_stage: str,
        history: list[Turn],
    ) -> None:
        self.interview_id = interview_id
        self.true_stage = true_stage
        self.history = history


class StageEvaluator:
    """对结构化面经运行阶段预测，计算 accuracy 等指标。"""

    def __init__(
        self,
        predictor: StagePredictor,
        concurrency: int = 5,
        seed: int = 42,
    ) -> None:
        self.predictor = predictor
        self.concurrency = concurrency
        self.rng = random.Random(seed)

    def _extract_samples(
        self,
        interviews: list[dict[str, Any]],
        samples_per_interview: int,
    ) -> list[StageEvalSample]:
        samples: list[StageEvalSample] = []
        for interview in interviews:
            interview_id = str(interview.get("interview_id", ""))
            raw_turns: list[dict[str, Any]] = interview.get("turns") or []
            if len(raw_turns) < _MIN_TURNS:
                continue

            # 有效 cut 范围：[2, len-1)（保证 history >= 2 条，且下一条存在）
            valid_indices = list(range(2, len(raw_turns)))
            if not valid_indices:
                continue

            cut_indices = self.rng.sample(
                valid_indices, min(samples_per_interview, len(valid_indices))
            )

            for cut_idx in cut_indices:
                history_raw = raw_turns[:cut_idx]
                history_turns = [_rebuild_turn(t) for t in history_raw]
                history_turns_clean = [t for t in history_turns if t is not None]
                if len(history_turns_clean) < 2:
                    continue

                true_stage = str(raw_turns[cut_idx - 1].get("stage") or "intro")
                samples.append(
                    StageEvalSample(
                        interview_id=interview_id,
                        true_stage=true_stage,
                        history=history_turns_clean,
                    )
                )
        return samples

    async def evaluate(
        self,
        interviews: list[dict[str, Any]],
        samples_per_interview: int = 3,
    ) -> StageEvalResult:
        """主评估入口。"""
        samples = self._extract_samples(interviews, samples_per_interview)
        log.info(
            "stage_evaluator.samples_extracted",
            interviews=len(interviews),
            samples=len(samples),
        )

        semaphore = asyncio.Semaphore(self.concurrency)
        true_labels: list[str] = []
        pred_labels: list[str] = []
        error_count = 0

        async def _predict_one(sample: StageEvalSample) -> tuple[str, str | None]:
            async with semaphore:
                try:
                    pred = await self.predictor.predict(sample.history)
                    return sample.true_stage, pred
                except Exception as exc:  # noqa: BLE001
                    log.error(
                        "stage_evaluator.predict_error",
                        interview_id=sample.interview_id,
                        error=str(exc),
                    )
                    return sample.true_stage, None

        try:
            from tqdm.asyncio import tqdm as atqdm  # type: ignore[import-untyped]
        except ImportError:
            from tqdm import tqdm as atqdm  # type: ignore[import-untyped]

        tasks = [_predict_one(s) for s in samples]
        async for coro in atqdm(
            asyncio.as_completed(tasks), total=len(tasks), desc="[stage-eval]"
        ):
            true, pred = await coro
            if pred is None:
                error_count += 1
                continue
            true_labels.append(true)
            pred_labels.append(pred)

        result = compute_metrics(true_labels, pred_labels)
        log.info(
            "stage_evaluator.done",
            total=len(samples),
            evaluated=len(true_labels),
            errors=error_count,
            accuracy=result.accuracy,
        )
        return result
