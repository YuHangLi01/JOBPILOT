"""Replay 主运行器。"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from jobpilot_agent.evaluation.replay.metrics import compute_rank, cosine_similarity
from jobpilot_agent.evaluation.replay.schema import ReplayPair, ReplayResult
from jobpilot_agent.graphs.interview.interviewer_core import InterviewerCore, InterviewerInput
from jobpilot_agent.graphs.interview.state import Turn
from jobpilot_agent.graphs.interview.transcript import count_stage_turns
from jobpilot_agent.logging_setup import get_logger
from jobpilot_agent.retrieval.embedding import BaseEmbedder

log = get_logger(__name__)

_TOP_K = 5


def _rebuild_turns(raw: list[dict[str, Any]]) -> list[Turn]:
    """将面经原始 turns 重建为 Turn 对象。"""
    turns = []
    for t in raw:
        try:
            stage = t.get("stage") or "intro"
            turns.append(
                Turn(
                    turn_id=int(t.get("turn_id", 0)),
                    role=t["role"],
                    content=str(t.get("content", "")),
                    stage=stage,  # type: ignore[arg-type]
                )
            )
        except Exception:  # noqa: BLE001
            pass
    return turns


class ReplayRunner:
    """并发执行 Replay 评估，支持断点续跑。"""

    def __init__(self, core: InterviewerCore, embedder: BaseEmbedder, concurrency: int = 3) -> None:
        self.core = core
        self.embedder = embedder
        self.concurrency = concurrency

    async def run_one(self, pair: ReplayPair) -> ReplayResult:
        """执行单个 Pair 的评估。"""
        start = time.monotonic()

        try:
            turns = _rebuild_turns(pair.history_turns_raw)
            stage_round = count_stage_turns(turns, pair.stage) // 2  # type: ignore[arg-type]

            inp = InterviewerInput(
                company=pair.company,
                position=pair.position,
                stage=pair.stage,  # type: ignore[arg-type]
                candidate_profile=None,  # Replay 不使用档案
                transcript=turns,
                stage_round=stage_round,
                max_stage_rounds=5,
            )

            # 生成 top-k 候选问题
            candidates = await self.core.generate_top_k_questions(inp, k=_TOP_K)
            bot_top_k_texts = [c.content for c in candidates]
            bot_next = candidates[0].content if candidates else ""

            # 语义相似度（bot_next vs real）
            real_emb = await self.embedder.embed_one(pair.real_next_question)
            bot_emb = await self.embedder.embed_one(bot_next)
            sim = cosine_similarity(bot_emb, real_emb)

            # Rank：候选列表中哪个最接近真实追问
            cand_embs = await self.embedder.embed_texts(bot_top_k_texts)
            rank, in_top_3, in_top_5 = compute_rank(
                real_emb=real_emb,
                cand_embs=[cand_embs[i] for i in range(len(bot_top_k_texts))],
            )

            latency_ms = int((time.monotonic() - start) * 1000)
            log.debug(
                "replay.pair_done",
                pair_id=pair.pair_id,
                sim=round(sim, 4),
                rank=rank,
                latency_ms=latency_ms,
            )
            return ReplayResult(
                pair_id=pair.pair_id,
                stage=pair.stage,
                bot_next_question=bot_next,
                bot_top_k_questions=bot_top_k_texts,
                semantic_similarity=sim,
                rank_in_top_k=rank,
                in_top_3=in_top_3,
                in_top_5=in_top_5,
                latency_ms=latency_ms,
                tokens_used=0,  # InterviewerCore 不暴露 usage 给 generate_top_k
            )

        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - start) * 1000)
            log.error("replay.pair_error", pair_id=pair.pair_id, error=str(exc))
            return ReplayResult(
                pair_id=pair.pair_id,
                stage=pair.stage,
                bot_next_question="",
                bot_top_k_questions=[],
                semantic_similarity=0.0,
                rank_in_top_k=99,
                in_top_3=False,
                in_top_5=False,
                latency_ms=latency_ms,
                tokens_used=0,
                error=f"{type(exc).__name__}: {exc}",
            )

    async def run_all(
        self,
        pairs: list[ReplayPair],
        output_path: str | Path,
        checkpoint_every: int = 20,
    ) -> list[ReplayResult]:
        """并发执行所有 Pair，支持断点续跑。"""
        try:
            from tqdm.asyncio import tqdm as atqdm  # type: ignore[import-untyped]
        except ImportError:
            from tqdm import tqdm as atqdm  # type: ignore[import-untyped]

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 断点续跑：读取已处理的 pair_id
        completed_ids: set[str] = set()
        if out_path.exists():
            with open(out_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rec = json.loads(line)
                            completed_ids.add(rec["pair_id"])
                        except Exception:  # noqa: BLE001
                            pass
            log.info("run_all.resume", completed=len(completed_ids), total=len(pairs))

        pending = [p for p in pairs if p.pair_id not in completed_ids]
        log.info("run_all.start", pending=len(pending), concurrency=self.concurrency)

        # 预热 embedder（BGEM3 首次 load 是同步 CPU 密集型）
        try:
            from jobpilot_agent.retrieval.embedding import BGEM3Embedder

            if isinstance(self.embedder, BGEM3Embedder):
                log.info("run_all.warmup_embedder")
                await asyncio.to_thread(self.embedder._load_model)
                log.info("run_all.embedder_warmed")
        except Exception as e:  # noqa: BLE001
            log.warning("run_all.warmup_failed", error=str(e))

        semaphore = asyncio.Semaphore(self.concurrency)
        results: list[ReplayResult] = []
        buffer: list[ReplayResult] = []

        async def _run_with_sem(pair: ReplayPair) -> ReplayResult:
            async with semaphore:
                return await self.run_one(pair)

        tasks = [_run_with_sem(p) for p in pending]

        async for coro in atqdm(asyncio.as_completed(tasks), total=len(tasks), desc="[replay]"):
            result = await coro
            results.append(result)
            buffer.append(result)

            if len(buffer) >= checkpoint_every:
                _append_results(out_path, buffer)
                log.info("run_all.checkpoint", written=len(buffer))
                buffer.clear()

        if buffer:
            _append_results(out_path, buffer)
            log.info("run_all.checkpoint_final", written=len(buffer))

        success_count = sum(1 for r in results if r.error is None)
        log.info(
            "run_all.done",
            total=len(results),
            success=success_count,
            failed=len(results) - success_count,
        )
        return results


def _append_results(path: Path, results: list[ReplayResult]) -> None:
    with open(path, "a", encoding="utf-8") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")
