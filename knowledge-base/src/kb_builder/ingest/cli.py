"""`kb-ingest` 命令行入口（click）。

    kb-ingest rebuild-jd        --input data/labeled/jd_labeled.jsonl
    kb-ingest rebuild-interview --input data/clean/interview_structured_filtered.jsonl
    kb-ingest rebuild-user      --input-dir data/user_samples/
    kb-ingest rebuild-all
    kb-ingest stats
    kb-ingest drop-and-rebuild --yes
    kb-ingest report --output data/kb_report.md
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import click

from jobpilot_agent.retrieval import CollectionName, get_retriever
from jobpilot_agent.retrieval.vector_store import get_vector_store
from kb_builder.ingest.orchestrator import IngestReport, KnowledgeBaseBuilder

DEFAULT_JD_PATH = Path("data/labeled/jd_labeled.jsonl")
DEFAULT_INTERVIEW_PATH = Path("data/clean/interview_structured_filtered.jsonl")
DEFAULT_USER_DIR = Path("data/user_samples")


def _async(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def _print_report(name: str, rep: IngestReport) -> None:
    stats = rep.chunks_per_doc_stats
    click.echo(
        f"  {name:12s} {rep.total_docs:4d} docs / {rep.total_chunks:5d} chunks "
        f"(mean {stats.mean:.1f}, median {stats.median:.1f}, "
        f"min {stats.min}, max {stats.max})  "
        f"embed+upsert {rep.embedding_upsert_time_sec:.1f}s  "
        f"bm25 {rep.bm25_save_time_sec:.2f}s  "
        f"failed={len(rep.failed_docs)}"
    )


# ---------------------------------------------------------------------------
# CLI root
# ---------------------------------------------------------------------------


@click.group()
def main() -> None:
    """JobPilot knowledge-base ingest CLI."""


# ---------------------------------------------------------------------------
# rebuild-*
# ---------------------------------------------------------------------------


@main.command("rebuild-jd")
@click.option("--input", "input_path", type=click.Path(exists=True, path_type=Path), default=DEFAULT_JD_PATH)
@click.option("--batch-size", type=int, default=50)
def rebuild_jd(input_path: Path, batch_size: int) -> None:
    builder = KnowledgeBaseBuilder()
    rep = _async(builder.rebuild_jd_kb(input_path, batch_size=batch_size))
    _print_report("jd_kb", rep)


@main.command("rebuild-interview")
@click.option("--input", "input_path", type=click.Path(exists=True, path_type=Path), default=DEFAULT_INTERVIEW_PATH)
@click.option("--batch-size", type=int, default=50)
def rebuild_interview(input_path: Path, batch_size: int) -> None:
    builder = KnowledgeBaseBuilder()
    rep = _async(builder.rebuild_interview_kb(input_path, batch_size=batch_size))
    _print_report("interview_kb", rep)


@main.command("rebuild-user")
@click.option(
    "--input-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=DEFAULT_USER_DIR,
)
def rebuild_user(input_dir: Path) -> None:
    builder = KnowledgeBaseBuilder()
    rep = _async(builder.rebuild_user_kb(input_dir))
    _print_report("user_kb", rep)


@main.command("rebuild-all")
@click.option("--jd-input", type=click.Path(exists=True, path_type=Path), default=DEFAULT_JD_PATH)
@click.option("--interview-input", type=click.Path(exists=True, path_type=Path), default=DEFAULT_INTERVIEW_PATH)
@click.option("--user-input-dir", type=click.Path(exists=True, file_okay=False, path_type=Path), default=DEFAULT_USER_DIR)
@click.option("--batch-size", type=int, default=50)
def rebuild_all(
    jd_input: Path,
    interview_input: Path,
    user_input_dir: Path,
    batch_size: int,
) -> None:
    builder = KnowledgeBaseBuilder()
    reports = _async(
        builder.rebuild_all(
            jd_input=jd_input,
            interview_input=interview_input,
            user_input_dir=user_input_dir,
            batch_size=batch_size,
        )
    )
    click.echo("Ingest summary:")
    for name, rep in reports.items():
        _print_report(name, rep)


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def _collect_stats() -> list[tuple[str, int, float]]:
    """返回 [(collection_name, vector_count, bm25_file_size_mb), ...]."""
    from jobpilot_agent.config import get_settings

    settings = get_settings()
    vs = get_vector_store()
    bm25_dir = Path(settings.bm25_index_dir)

    rows: list[tuple[str, int, float]] = []
    for col in (CollectionName.JD_KB, CollectionName.INTERVIEW_KB, CollectionName.USER_KB):
        try:
            cnt = vs.count(col)
        except Exception:
            cnt = 0
        pkl = bm25_dir / f"{col.value}.pkl"
        mb = pkl.stat().st_size / (1024 * 1024) if pkl.exists() else 0.0
        rows.append((col.value, cnt, mb))
    return rows


@main.command("stats")
def stats() -> None:
    click.echo("Knowledge-base stats:")
    for name, cnt, bm25_mb in _collect_stats():
        click.echo(f"  {name:12s} vectors={cnt:5d}   bm25_pkl={bm25_mb:.2f} MB")


# ---------------------------------------------------------------------------
# drop-and-rebuild
# ---------------------------------------------------------------------------


@main.command("drop-and-rebuild")
@click.option("--yes", is_flag=True, help="必须显式指定 --yes 才会执行删除")
@click.option("--jd-input", type=click.Path(exists=True, path_type=Path), default=DEFAULT_JD_PATH)
@click.option("--interview-input", type=click.Path(exists=True, path_type=Path), default=DEFAULT_INTERVIEW_PATH)
@click.option("--user-input-dir", type=click.Path(exists=True, file_okay=False, path_type=Path), default=DEFAULT_USER_DIR)
def drop_and_rebuild(
    yes: bool,
    jd_input: Path,
    interview_input: Path,
    user_input_dir: Path,
) -> None:
    if not yes:
        click.echo("❌ 拒绝执行：drop-and-rebuild 是危险操作，必须传入 --yes 确认。")
        raise SystemExit(1)

    vs = get_vector_store()
    for col in (CollectionName.JD_KB, CollectionName.INTERVIEW_KB, CollectionName.USER_KB):
        try:
            vs.drop(col)
            click.echo(f"dropped {col.value}")
        except Exception as exc:
            click.echo(f"drop failed for {col.value}: {exc}")

    builder = KnowledgeBaseBuilder()
    reports = _async(
        builder.rebuild_all(
            jd_input=jd_input,
            interview_input=interview_input,
            user_input_dir=user_input_dir,
        )
    )
    click.echo("Rebuild summary:")
    for name, rep in reports.items():
        _print_report(name, rep)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


@main.command("report")
@click.option("--output", "output_path", type=click.Path(path_type=Path), default=Path("data/kb_report.md"))
def report(output_path: Path) -> None:
    rows = _collect_stats()
    lines = [
        "# Knowledge Base Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| Collection | Vectors | BM25 pickle (MB) |",
        "|-----------|---------|------------------|",
    ]
    for name, cnt, mb in rows:
        lines.append(f"| `{name}` | {cnt} | {mb:.2f} |")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    click.echo(f"Report written to {output_path}")


if __name__ == "__main__":
    main()
