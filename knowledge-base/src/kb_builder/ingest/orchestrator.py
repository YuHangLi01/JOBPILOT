"""知识库灌库编排器。

把 splitter 产出的 chunk 转成 `jobpilot_agent.retrieval.types.Document`，
交给对应 collection 的 `HybridRetriever.add_documents()`，最后把
BM25 索引持久化到 settings.bm25_index_dir 下。

设计取舍：
- `HybridRetriever.add_documents` 一次搞定 embed + Milvus upsert + BM25 merge，
  所以这里无法再细分到各阶段耗时；`IngestReport.embedding_upsert_time_sec`
  代表这一整段的墙钟时间。BM25 save 是独立一次，另记。
- batch_size=50：与 embedding/upsert 的吞吐同数量级；失败时以批为单位记录失败的
  source_id（而非整批直接中断）。
"""

from __future__ import annotations

import json
import logging
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from pydantic import BaseModel
from tqdm import tqdm

from jobpilot_agent.config import get_settings
from jobpilot_agent.retrieval import (
    CollectionName,
    Document,
    HybridRetriever,
    get_retriever,
)
from kb_builder.ingest.splitters import (
    split_interview,
    split_jd,
    split_user_doc,
)
from kb_builder.models import (
    ChunksPerDocStats,
    IngestReport,
    InterviewChunk,
    JDChunk,
    LabeledJD,
    StructuredInterview,
    UserChunk,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _read_jsonl(path: str | Path) -> Iterable[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"输入文件不存在：{p}")
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _chunks_per_doc_stats(chunks_per_doc: list[int]) -> ChunksPerDocStats:
    if not chunks_per_doc:
        return ChunksPerDocStats(mean=0.0, median=0.0, min=0, max=0)
    return ChunksPerDocStats(
        mean=round(statistics.mean(chunks_per_doc), 2),
        median=round(float(statistics.median(chunks_per_doc)), 2),
        min=min(chunks_per_doc),
        max=max(chunks_per_doc),
    )


def _chunk_to_document(
    chunk: JDChunk | InterviewChunk | UserChunk,
    collection: CollectionName,
) -> Document:
    payload = chunk.model_dump()
    doc_id = payload.pop("doc_id")
    text = payload.pop("text")
    # 其余都进入 metadata；None / "" 值会在 Milvus search 输出时被过滤掉
    return Document(
        doc_id=doc_id,
        collection=collection,
        text=text,
        metadata={k: v for k, v in payload.items() if v is not None},
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class KnowledgeBaseBuilder:
    """灌库编排器（每个 collection 一个 retriever）。

    Example:
        >>> builder = KnowledgeBaseBuilder()
        >>> await builder.rebuild_jd_kb("data/labeled/jd_labeled.jsonl")
    """

    def __init__(
        self,
        retriever_factory: Callable[[CollectionName], HybridRetriever] = get_retriever,
        bm25_dir: str | Path | None = None,
        report_dir: str | Path | None = None,
    ) -> None:
        settings = get_settings()
        self._retriever_factory = retriever_factory
        self._bm25_dir = Path(bm25_dir or settings.bm25_index_dir)
        self._report_dir = Path(report_dir or "./data")

    # ------------------------------------------------------------------
    # 单 collection 重建
    # ------------------------------------------------------------------

    async def rebuild_jd_kb(
        self,
        input_path: str | Path,
        batch_size: int = 50,
    ) -> IngestReport:
        retriever = self._retriever_factory(CollectionName.JD_KB)
        total_docs = 0
        total_chunks = 0
        chunks_per_doc: list[int] = []
        failed: list[str] = []

        embed_upsert_seconds = 0.0

        buffer: list[Document] = []
        rows = list(_read_jsonl(input_path))
        progress = tqdm(rows, desc="jd_kb", unit="jd")

        async def flush() -> None:
            nonlocal embed_upsert_seconds
            if not buffer:
                return
            t0 = time.monotonic()
            await retriever.add_documents(CollectionName.JD_KB, buffer)
            embed_upsert_seconds += time.monotonic() - t0
            buffer.clear()

        for row in progress:
            jd_id = str(row.get("jd_id") or "")
            try:
                jd = LabeledJD.model_validate(row)
                chunks = split_jd(jd)
            except Exception as exc:
                logger.warning("[jd_kb] parse/split failed for %s: %s", jd_id, exc)
                failed.append(jd_id)
                continue

            if not chunks:
                failed.append(jd_id)
                continue

            total_docs += 1
            total_chunks += len(chunks)
            chunks_per_doc.append(len(chunks))

            for c in chunks:
                buffer.append(_chunk_to_document(c, CollectionName.JD_KB))

            if len(buffer) >= batch_size:
                await flush()

        await flush()

        bm25_save_sec = await self._persist_bm25(retriever, CollectionName.JD_KB)

        return IngestReport(
            collection=CollectionName.JD_KB.value,
            total_docs=total_docs,
            total_chunks=total_chunks,
            chunks_per_doc_stats=_chunks_per_doc_stats(chunks_per_doc),
            embedding_upsert_time_sec=round(embed_upsert_seconds, 3),
            bm25_save_time_sec=round(bm25_save_sec, 3),
            failed_docs=failed,
        )

    async def rebuild_interview_kb(
        self,
        input_path: str | Path,
        batch_size: int = 50,
    ) -> IngestReport:
        retriever = self._retriever_factory(CollectionName.INTERVIEW_KB)
        total_docs = 0
        total_chunks = 0
        chunks_per_doc: list[int] = []
        failed: list[str] = []

        embed_upsert_seconds = 0.0
        buffer: list[Document] = []
        rows = list(_read_jsonl(input_path))
        progress = tqdm(rows, desc="interview_kb", unit="int")

        async def flush() -> None:
            nonlocal embed_upsert_seconds
            if not buffer:
                return
            t0 = time.monotonic()
            await retriever.add_documents(CollectionName.INTERVIEW_KB, buffer)
            embed_upsert_seconds += time.monotonic() - t0
            buffer.clear()

        for row in progress:
            interview_id = str(row.get("interview_id") or "")
            try:
                interview = StructuredInterview.model_validate(row)
                chunks = split_interview(interview)
            except Exception as exc:
                logger.warning(
                    "[interview_kb] parse/split failed for %s: %s", interview_id, exc
                )
                failed.append(interview_id)
                continue

            if not chunks:
                failed.append(interview_id)
                continue

            total_docs += 1
            total_chunks += len(chunks)
            chunks_per_doc.append(len(chunks))

            for c in chunks:
                buffer.append(_chunk_to_document(c, CollectionName.INTERVIEW_KB))

            if len(buffer) >= batch_size:
                await flush()

        await flush()

        bm25_save_sec = await self._persist_bm25(retriever, CollectionName.INTERVIEW_KB)

        return IngestReport(
            collection=CollectionName.INTERVIEW_KB.value,
            total_docs=total_docs,
            total_chunks=total_chunks,
            chunks_per_doc_stats=_chunks_per_doc_stats(chunks_per_doc),
            embedding_upsert_time_sec=round(embed_upsert_seconds, 3),
            bm25_save_time_sec=round(bm25_save_sec, 3),
            failed_docs=failed,
        )

    async def rebuild_user_kb(
        self,
        input_dir: str | Path,
    ) -> IngestReport:
        retriever = self._retriever_factory(CollectionName.USER_KB)
        total_docs = 0
        total_chunks = 0
        chunks_per_doc: list[int] = []
        failed: list[str] = []

        embed_upsert_seconds = 0.0
        buffer: list[Document] = []

        dir_path = Path(input_dir)
        if not dir_path.exists():
            raise FileNotFoundError(f"用户简历目录不存在：{dir_path}")

        md_files = sorted(dir_path.glob("*.md"))
        if not md_files:
            logger.warning("[user_kb] 未发现 .md 简历文件：%s", dir_path)

        progress = tqdm(md_files, desc="user_kb", unit="file")
        for md in progress:
            # 文件名 "u_default_resume.md" → user_id="u_default"
            user_id = md.stem
            if user_id.endswith("_resume"):
                user_id = user_id[: -len("_resume")]
            try:
                chunks = split_user_doc(md, user_id=user_id)
            except Exception as exc:
                logger.warning("[user_kb] split failed for %s: %s", md.name, exc)
                failed.append(md.name)
                continue

            if not chunks:
                failed.append(md.name)
                continue

            total_docs += 1
            total_chunks += len(chunks)
            chunks_per_doc.append(len(chunks))

            for c in chunks:
                # user_kb 的 doc_id 基于文件，不会与其他 user 冲突，所以每文件单独一次 flush
                buffer.append(_chunk_to_document(c, CollectionName.USER_KB))

        if buffer:
            t0 = time.monotonic()
            await retriever.add_documents(CollectionName.USER_KB, buffer)
            embed_upsert_seconds += time.monotonic() - t0
            buffer.clear()

        bm25_save_sec = await self._persist_bm25(retriever, CollectionName.USER_KB)

        return IngestReport(
            collection=CollectionName.USER_KB.value,
            total_docs=total_docs,
            total_chunks=total_chunks,
            chunks_per_doc_stats=_chunks_per_doc_stats(chunks_per_doc),
            embedding_upsert_time_sec=round(embed_upsert_seconds, 3),
            bm25_save_time_sec=round(bm25_save_sec, 3),
            failed_docs=failed,
        )

    # ------------------------------------------------------------------
    # 全量
    # ------------------------------------------------------------------

    async def rebuild_all(
        self,
        jd_input: str | Path,
        interview_input: str | Path,
        user_input_dir: str | Path,
        batch_size: int = 50,
    ) -> dict[str, IngestReport]:
        reports: dict[str, IngestReport] = {}
        reports["jd_kb"] = await self.rebuild_jd_kb(jd_input, batch_size=batch_size)
        reports["interview_kb"] = await self.rebuild_interview_kb(
            interview_input, batch_size=batch_size
        )
        reports["user_kb"] = await self.rebuild_user_kb(user_input_dir)

        self._dump_reports(reports)
        return reports

    # ------------------------------------------------------------------
    # 私有
    # ------------------------------------------------------------------

    async def _persist_bm25(
        self, retriever: HybridRetriever, collection: CollectionName
    ) -> float:
        target = self._bm25_dir / f"{collection.value}.pkl"
        t0 = time.monotonic()
        # 访问私有字段 _bm25：两端都是第一方代码，接受耦合
        retriever._bm25.save(target)  # noqa: SLF001
        return time.monotonic() - t0

    def _dump_reports(self, reports: dict[str, IngestReport]) -> None:
        self._report_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = self._report_dir / f"ingest_report_{ts}.json"
        body = {name: _dump_model(rep) for name, rep in reports.items()}
        out.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Ingest report written to %s", out)


def _dump_model(m: BaseModel) -> dict:
    return m.model_dump()
