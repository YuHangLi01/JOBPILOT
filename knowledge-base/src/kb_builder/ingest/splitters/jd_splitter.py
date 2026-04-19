"""JD 切片器。

优先按段落头（岗位职责 / 任职要求 / 加分项）切；
任何识别不出结构的 JD 退化成固定 token 切片，chunk_type="full"。
"""

from __future__ import annotations

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter

from kb_builder.extractors.jd_fields import extract_all
from kb_builder.models import JDChunk, JDChunkType, LabeledJD

# 段落头识别正则 —— 捕获后面的内容一直到下一个段落头为止
_SECTION_PATTERNS: list[tuple[JDChunkType, re.Pattern[str]]] = [
    (
        "responsibilities",
        re.compile(r"(?:岗位职责|工作内容|职位描述|Responsibilities|Job Description)\s*[:：]?"),
    ),
    (
        "requirements",
        re.compile(r"(?:任职要求|岗位要求|职位要求|任职资格|Requirements|Qualifications)\s*[:：]?"),
    ),
    (
        "perks",
        re.compile(r"(?:加分项|优先条件|优先|Preferred|Plus|Nice to have)\s*[:：]?"),
    ),
]

_FALLBACK_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=400,
    chunk_overlap=40,
    separators=["\n\n", "\n", "。", "；", ";", "，", ",", " ", ""],
)

# 文本过短直接整段一个 chunk
_MIN_SECTION_SPLIT_LEN = 200


def _find_section_spans(text: str) -> list[tuple[JDChunkType, int, int]]:
    """找出所有段落头的位置并把文本切成 (chunk_type, start, end) 段。"""
    hits: list[tuple[JDChunkType, int]] = []
    for chunk_type, pat in _SECTION_PATTERNS:
        for m in pat.finditer(text):
            hits.append((chunk_type, m.end()))

    if not hits:
        return []

    hits.sort(key=lambda x: x[1])
    spans: list[tuple[JDChunkType, int, int]] = []
    for i, (chunk_type, start) in enumerate(hits):
        end = hits[i + 1][1] if i + 1 < len(hits) else len(text)
        spans.append((chunk_type, start, end))
    return spans


def split_jd(jd: LabeledJD) -> list[JDChunk]:
    """把一条 `LabeledJD` 按段落切成 1..N 个 chunk。"""
    text = jd.jd_text.strip()
    extracted = extract_all(text, sub_type_fallback=jd.labels.sub_type)

    base_meta = {
        "source_id": jd.jd_id,
        "company": extracted["company"],
        "position": extracted["position"],
        "location": extracted["location"],
        "job_type": jd.labels.job_type,
        "sub_type": jd.labels.sub_type,
        "level": jd.labels.level,
        "locale": jd.labels.locale,
        "channel": jd.labels.channel,
    }

    spans = _find_section_spans(text)

    chunks: list[JDChunk] = []

    if spans and len(text) >= _MIN_SECTION_SPLIT_LEN:
        for idx, (chunk_type, start, end) in enumerate(spans):
            body = text[start:end].strip()
            if not body:
                continue
            chunks.append(
                JDChunk(
                    doc_id=f"jd-{jd.jd_id}-{idx}",
                    text=body,
                    chunk_index=idx,
                    chunk_type=chunk_type,
                    **base_meta,
                )
            )

    if chunks:
        return chunks

    # Fallback：整段按 400 token 切，chunk_type=full
    pieces = _FALLBACK_SPLITTER.split_text(text) or [text]
    for idx, body in enumerate(pieces):
        body = body.strip()
        if not body:
            continue
        chunks.append(
            JDChunk(
                doc_id=f"jd-{jd.jd_id}-{idx}",
                text=body,
                chunk_index=idx,
                chunk_type="full",
                **base_meta,
            )
        )

    return chunks
