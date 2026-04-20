"""RAGAS 评估运行器。

两个职责：
1. RagasCollector — 运行 JD 路由图，收集每条样本的 contexts + answer
2. RagasEvaluator — 调用 RAGAS 库计算四项指标（火山方舟 LLM 替代 OpenAI）

用法：
    collector = RagasCollector(get_jd_routing_graph())
    examples = await collector.collect(examples, concurrency=3)

    evaluator = RagasEvaluator()
    results = await evaluator.evaluate(examples)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from jobpilot_agent.evaluation.ragas.schema import RagasExample, RagasResult
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)


# ── Collect ────────────────────────────────────────────────────────────────────


class RagasCollector:
    """对每条 RagasExample 运行 JD 路由图，填充 contexts 和 answer。"""

    def __init__(self, graph) -> None:
        self.graph = graph

    async def collect_one(self, example: RagasExample) -> RagasExample:
        """运行单条样本，填充 contexts 和 answer。"""
        try:
            final_state = await self.graph.ainvoke({
                "request_id": example.example_id,
                "user_id": "ragas_collector",
                "jd_text": example.jd_text,
                "user_context": {"preferred_lang": "zh"},
                "skill_outputs": [],
                "metadata": {},
                "errors": [],
            })

            # 提取 contexts：interview_rag skill 的原始检索文本
            skill_outputs: list[dict] = final_state.get("skill_outputs") or []
            rag_out = next(
                (o for o in skill_outputs
                 if o.get("skill_name") == "interview_rag" and o.get("success")),
                None,
            )
            if rag_out:
                example.contexts = rag_out.get("data", {}).get("raw_retrieved_texts") or []

            # 提取 answer：final_result.interview_questions 拼接为文本
            questions = (final_state.get("final_result") or {}).get("interview_questions") or []
            if questions:
                lines = []
                for q in questions:
                    lines.append(f"问题：{q.get('question', '')}")
                    for pt in q.get("answer_points", []):
                        lines.append(f"  - {pt}")
                example.answer = "\n".join(lines)

        except Exception as exc:  # noqa: BLE001
            log.warning("collect_one.failed", example_id=example.example_id, error=str(exc))

        return example

    async def collect(
        self,
        examples: list[RagasExample],
        concurrency: int = 3,
        output_path: Optional[str] = None,
        checkpoint_every: int = 10,
    ) -> list[RagasExample]:
        """并发收集所有样本的 contexts + answer，支持断点续跑。"""
        try:
            from tqdm.asyncio import tqdm as atqdm
        except ImportError:
            from tqdm import tqdm as atqdm  # type: ignore[no-redef]

        # 断点续跑
        completed_ids: set[str] = set()
        completed: dict[str, RagasExample] = {}
        if output_path and Path(output_path).exists():
            with open(output_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            ex = RagasExample.model_validate_json(line)
                            completed_ids.add(ex.example_id)
                            completed[ex.example_id] = ex
                        except Exception:  # noqa: BLE001
                            pass
            log.info("collect.resume", completed=len(completed_ids))

        pending = [e for e in examples if e.example_id not in completed_ids]
        semaphore = asyncio.Semaphore(concurrency)
        results: list[RagasExample] = list(completed.values())
        buffer: list[RagasExample] = []

        async def _run(ex: RagasExample) -> RagasExample:
            async with semaphore:
                return await self.collect_one(ex)

        tasks = [_run(ex) for ex in pending]
        async for coro in atqdm(asyncio.as_completed(tasks), total=len(tasks), desc="[collect]"):
            ex = await coro
            results.append(ex)
            buffer.append(ex)

            if output_path and len(buffer) >= checkpoint_every:
                _append_examples(output_path, buffer)
                buffer.clear()

        if output_path and buffer:
            _append_examples(output_path, buffer)

        ctx_filled = sum(1 for e in results if e.contexts)
        log.info("collect.done", total=len(results), with_contexts=ctx_filled)
        return results


def _append_examples(path: str, examples: list[RagasExample]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for ex in examples:
            f.write(ex.model_dump_json() + "\n")


# ── Evaluate ───────────────────────────────────────────────────────────────────


class RagasEvaluator:
    """调用 RAGAS 库计算四项检索评估指标。

    使用火山方舟 doubao 替代 OpenAI。
    """

    def __init__(self) -> None:
        pass

    def _get_ragas_llm(self):
        from langchain_openai import ChatOpenAI  # noqa: PLC0415
        from ragas.llms import LangchainLLMWrapper  # noqa: PLC0415

        from jobpilot_agent.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        llm = ChatOpenAI(
            model=settings.llm_model,
            openai_api_base=settings.llm_api_base_url,
            openai_api_key=settings.llm_api_key,
            temperature=0,
        )
        return LangchainLLMWrapper(llm)

    def _get_ragas_embeddings(self):
        from langchain_community.embeddings import HuggingFaceEmbeddings  # noqa: PLC0415
        from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: PLC0415

        from jobpilot_agent.config import get_settings  # noqa: PLC0415

        settings = get_settings()
        emb = HuggingFaceEmbeddings(model_name=settings.embedding_model_name)
        return LangchainEmbeddingsWrapper(emb)

    async def evaluate(
        self,
        examples: list[RagasExample],
        limit: Optional[int] = None,
    ) -> list[RagasResult]:
        """对给定 examples 跑 RAGAS 四件套，返回 list[RagasResult]。"""
        from datasets import Dataset  # noqa: PLC0415
        from ragas import evaluate  # noqa: PLC0415
        from ragas.metrics import (  # noqa: PLC0415
            answer_relevancy,
            context_recall,
            context_relevancy,
            faithfulness,
        )
        from ragas.run_config import RunConfig  # noqa: PLC0415

        # 过滤有效样本：contexts 非空 + ground_truth 非空 + answer 非空
        valid = [
            e for e in examples
            if e.contexts and e.ground_truth and e.answer
        ]
        if limit:
            valid = valid[:limit]

        if not valid:
            log.warning("evaluate.no_valid_examples")
            return []

        log.info("evaluate.start", valid=len(valid), total=len(examples))

        # 构造 RAGAS Dataset
        ds = Dataset.from_list([
            {
                "question": e.question,
                "contexts": e.contexts,
                "answer": e.answer,
                "ground_truth": e.ground_truth,
            }
            for e in valid
        ])

        ragas_llm = self._get_ragas_llm()
        ragas_emb = self._get_ragas_embeddings()

        result = evaluate(
            dataset=ds,
            metrics=[context_relevancy, context_recall, faithfulness, answer_relevancy],
            llm=ragas_llm,
            embeddings=ragas_emb,
            run_config=RunConfig(max_workers=3, timeout=120),
        )

        df = result.to_pandas()

        ragas_results: list[RagasResult] = []
        for i, ex in enumerate(valid):
            row = df.iloc[i]
            ragas_results.append(RagasResult(
                example_id=ex.example_id,
                context_relevancy=float(row.get("context_relevancy", 0.0) or 0.0),
                context_recall=float(row.get("context_recall", 0.0) or 0.0),
                faithfulness=float(row.get("faithfulness", 0.0) or 0.0),
                answer_relevancy=float(row.get("answer_relevancy", 0.0) or 0.0),
            ))

        # 对无法评估的样本补充 error 记录
        evaluated_ids = {r.example_id for r in ragas_results}
        for ex in examples:
            if ex.example_id not in evaluated_ids:
                ragas_results.append(RagasResult(
                    example_id=ex.example_id,
                    error="skipped: empty contexts / ground_truth / answer",
                ))

        log.info("evaluate.done", evaluated=len(ragas_results))
        return ragas_results


def load_results(path: str) -> list[RagasResult]:
    """从 JSONL 加载 RagasResult 列表。"""
    results: list[RagasResult] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(RagasResult.model_validate_json(line))
                except Exception as exc:  # noqa: BLE001
                    log.warning("load_results.skip", error=str(exc))
    return results


def save_results(results: list[RagasResult], path: str) -> None:
    """将 RagasResult 列表写入 JSONL。"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")
