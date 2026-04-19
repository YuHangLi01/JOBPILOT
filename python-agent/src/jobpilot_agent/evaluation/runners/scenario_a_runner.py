"""场景 A 主运行器。

对每条 EvaluationExample 跑一次 LangGraph，收集完整的执行记录 (RunRecord)，
支持断点续跑和并发限流。

用法：
    runner = ScenarioARunner(graph=get_jd_routing_graph(), label="main")
    records = await runner.run_all(dataset, output_path="evaluation/runs/main.jsonl")
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from jobpilot_agent.evaluation.datasets.loader import EvaluationExample
from jobpilot_agent.logging_setup import get_logger

log = get_logger(__name__)

_NODE_NAMES = ["parse_jd", "classify_jd", "dispatch_skills", "invoke_skills_parallel", "merge_outputs", "final_synthesis"]


class RunRecord(BaseModel):
    """单次 LangGraph 执行的完整记录。

    Attributes:
        jd_id: 来自数据集的唯一 ID。
        run_label: 运行标签（"main" 或 "baseline"）。
        jd_text_len: JD 文本字符数。
        ground_truth_labels: 5 维分类 ground truth。
        ground_truth_expected_skills: 应触发的 Skill 列表。
        ground_truth_forbidden_skills: 不应触发的 Skill 列表。
        predicted_classification: 图输出的分类结果。
        predicted_invoked_skills: 图决策触发的 Skill 列表。
        predicted_skipped_skills: 图决策跳过的 Skill 列表。
        total_latency_ms: 端到端耗时（毫秒）。
        per_node_latency_ms: 各节点耗时（来自 state.metadata）。
        total_tokens: 总 token 消耗。
        llm_calls: LLM API 调用次数。
        external_calls: 外部 API 调用次数（不含 LLM）。
        success: 图是否成功完成（False 表示顶层异常）。
        errors: 图执行过程中的错误记录列表。
        final_result_preview: final_result.jd_summary 的前 200 字（用于人工抽查）。
        timestamp_utc: 执行时间（UTC）。
    """

    jd_id: str
    run_label: str = "main"
    jd_text_len: int

    # ── Ground truth ─────────────────────────────────────────────────
    ground_truth_labels: dict[str, Any]
    ground_truth_expected_skills: list[str]
    ground_truth_forbidden_skills: list[str]

    # ── 预测输出 ──────────────────────────────────────────────────────
    predicted_classification: dict[str, Any] = Field(default_factory=dict)
    predicted_invoked_skills: list[str] = Field(default_factory=list)
    predicted_skipped_skills: list[str] = Field(default_factory=list)

    # ── 度量 ──────────────────────────────────────────────────────────
    total_latency_ms: int = 0
    per_node_latency_ms: dict[str, int] = Field(default_factory=dict)
    total_tokens: int = 0
    llm_calls: int = 0
    external_calls: int = 0

    # ── 状态 ──────────────────────────────────────────────────────────
    success: bool = True
    errors: list[dict[str, Any]] = Field(default_factory=list)
    final_result_preview: Optional[str] = None
    timestamp_utc: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _extract_per_node_latency(metadata: dict[str, Any]) -> dict[str, int]:
    """从 state["metadata"] 提取各节点耗时（ms）。"""
    result: dict[str, int] = {}
    for node in _NODE_NAMES:
        node_meta = metadata.get(node)
        if isinstance(node_meta, dict) and "latency_ms" in node_meta:
            result[node] = int(node_meta["latency_ms"])
    return result


def _sum_tokens_from_metadata(metadata: dict[str, Any], skill_outputs: list[dict]) -> tuple[int, int]:
    """从 metadata 和 skill_outputs 中累加 tokens 和 llm_calls。

    Returns:
        (total_tokens, llm_calls)
    """
    tokens = 0
    calls = 0
    for node in ["parse_jd", "classify_jd", "final_synthesis"]:
        node_meta = metadata.get(node) or {}
        tokens += int(node_meta.get("tokens") or 0)
        if node_meta.get("tokens") or node_meta.get("error"):
            calls += 1
    # merge_outputs 里记录了 skill tokens 合计
    merge_meta = metadata.get("merge_outputs") or {}
    tokens += int(merge_meta.get("total_skill_tokens") or 0)
    # llm_calls from skill outputs
    for o in skill_outputs:
        calls += int(o.get("llm_calls") or 0)
    return tokens, calls


def _sum_external_calls(skill_outputs: list[dict]) -> int:
    return sum(int(o.get("external_calls") or 0) for o in skill_outputs)


class ScenarioARunner:
    """对评估数据集逐条运行 LangGraph，收集 RunRecord。

    特性：
    - asyncio.Semaphore 限制并发（避免打爆 LLM API）
    - tqdm 进度条
    - 每 checkpoint_every 条写入 output_path（断点续跑支持）
    - 单条失败不中断整体
    """

    def __init__(self, graph: Any, label: str = "main") -> None:
        self.graph = graph
        self.label = label

    async def run_one(self, example: EvaluationExample) -> RunRecord:
        """对单条样本执行图，返回 RunRecord。

        Args:
            example: 评估样本。

        Returns:
            RunRecord（无论成败均有效）。
        """
        start = time.monotonic()
        initial_state: dict[str, Any] = {
            "request_id": example.jd_id,
            "user_id": "eval_runner",
            "jd_text": example.jd_text,
            "user_context": {"preferred_lang": "zh"},
            "skill_outputs": [],
            "metadata": {},
            "errors": [],
        }

        try:
            final_state = await self.graph.ainvoke(initial_state)
            latency_ms = int((time.monotonic() - start) * 1000)

            metadata: dict = final_state.get("metadata") or {}
            skill_outputs: list[dict] = final_state.get("skill_outputs") or []
            total_tokens, llm_calls = _sum_tokens_from_metadata(metadata, skill_outputs)
            external_calls = _sum_external_calls(skill_outputs)

            final_result = final_state.get("final_result") or {}
            preview = str(final_result.get("jd_summary") or "")[:200] or None

            record = RunRecord(
                jd_id=example.jd_id,
                run_label=self.label,
                jd_text_len=len(example.jd_text),
                ground_truth_labels=example.labels,
                ground_truth_expected_skills=example.expected_skills,
                ground_truth_forbidden_skills=example.forbidden_skills,
                predicted_classification=final_state.get("classification") or {},
                predicted_invoked_skills=final_state.get("invoked_skills") or [],
                predicted_skipped_skills=final_state.get("skipped_skills") or [],
                total_latency_ms=latency_ms,
                per_node_latency_ms=_extract_per_node_latency(metadata),
                total_tokens=total_tokens,
                llm_calls=llm_calls,
                external_calls=external_calls,
                success=True,
                errors=final_state.get("errors") or [],
                final_result_preview=preview,
            )
            return record

        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.monotonic() - start) * 1000)
            log.error("run_one.error", jd_id=example.jd_id, error=str(exc))
            return RunRecord(
                jd_id=example.jd_id,
                run_label=self.label,
                jd_text_len=len(example.jd_text),
                ground_truth_labels=example.labels,
                ground_truth_expected_skills=example.expected_skills,
                ground_truth_forbidden_skills=example.forbidden_skills,
                total_latency_ms=latency_ms,
                success=False,
                errors=[{"node": "runner", "error": str(exc)}],
            )

    async def run_all(
        self,
        dataset: list[EvaluationExample],
        concurrency: int = 5,
        output_path: str | Path | None = None,
        checkpoint_every: int = 20,
    ) -> list[RunRecord]:
        """并发运行所有样本，支持断点续跑。

        Args:
            dataset: 评估样本列表。
            concurrency: 最大并发数（用于限制 LLM API 调用频率）。
            output_path: 结果写入路径（JSONL 格式）。None 则不落盘。
            checkpoint_every: 每处理这么多条就写一次磁盘。

        Returns:
            RunRecord 列表，顺序与 dataset 一致。
        """
        try:
            from tqdm.asyncio import tqdm as atqdm
        except ImportError:
            from tqdm import tqdm as atqdm  # type: ignore[no-redef]

        # ── 断点续跑：加载已完成的 jd_id ─────────────────────────────
        completed_ids: set[str] = set()
        if output_path is not None:
            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if out_path.exists():
                with open(out_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                rec = json.loads(line)
                                completed_ids.add(rec["jd_id"])
                            except Exception:  # noqa: BLE001
                                pass
                log.info(
                    "run_all.resume",
                    completed=len(completed_ids),
                    total=len(dataset),
                )

        pending = [ex for ex in dataset if ex.jd_id not in completed_ids]
        log.info("run_all.start", pending=len(pending), label=self.label)

        # ── 预热：初始化向量库 + 嵌入模型（避免首次调用阻塞 asyncio 事件循环）──
        # interview_rag 调用时会触发 BGEM3Embedder._load_model()（同步，CPU 密集），
        # 使用 asyncio.to_thread 在子线程预热，await 等待完成后再启动并发任务。
        try:
            from jobpilot_agent.retrieval.vector_store import get_vector_store
            from jobpilot_agent.retrieval.embedding import get_embedder, BGEM3Embedder
            get_vector_store()
            _embedder = get_embedder()
            if isinstance(_embedder, BGEM3Embedder):
                log.info("run_all.warmup_start", model=_embedder._model_name)
                await asyncio.to_thread(_embedder._load_model)
                log.info("run_all.embedder_warmed")
            else:
                log.info("run_all.embedder_warmed", provider="remote")
        except Exception as _warm_exc:  # noqa: BLE001
            log.warning("run_all.embedder_warm_failed", error=str(_warm_exc))

        semaphore = asyncio.Semaphore(concurrency)
        results: list[RunRecord] = []
        buffer: list[RunRecord] = []

        async def _run_with_sem(ex: EvaluationExample) -> RunRecord:
            async with semaphore:
                return await self.run_one(ex)

        tasks = [_run_with_sem(ex) for ex in pending]

        async for coro in atqdm(asyncio.as_completed(tasks), total=len(tasks), desc=f"[{self.label}]"):
            record = await coro
            results.append(record)
            buffer.append(record)

            if output_path is not None and len(buffer) >= checkpoint_every:
                _append_records(output_path, buffer)
                log.info("run_all.checkpoint", written=len(buffer))
                buffer.clear()

        # 写剩余
        if output_path is not None and buffer:
            _append_records(output_path, buffer)
            log.info("run_all.checkpoint_final", written=len(buffer))

        success_count = sum(1 for r in results if r.success)
        log.info(
            "run_all.done",
            total=len(results),
            success=success_count,
            failed=len(results) - success_count,
        )
        return results


def _append_records(path: str | Path, records: list[RunRecord]) -> None:
    """将 RunRecord 列表追加写入 JSONL 文件。"""
    with open(path, "a", encoding="utf-8") as f:
        for rec in records:
            f.write(rec.model_dump_json() + "\n")


def load_run_records(path: str | Path) -> list[RunRecord]:
    """从 JSONL 文件加载 RunRecord 列表。"""
    records: list[RunRecord] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(RunRecord.model_validate_json(line))
                except Exception as exc:  # noqa: BLE001
                    log.warning("load_run_records.skip", error=str(exc))
    return records
