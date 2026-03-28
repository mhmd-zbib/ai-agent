"""Ingestion service — orchestrates the 4-stage pipeline.

Replaces orchestrator.py. Runs Stage 1 -> 2 -> 3 -> 4 in sequence using the
stages/ layout, and maintains an in-memory job store for SSE progress streaming.

Backward-compatible: ``ingest`` and ``job_events`` remain importable from here.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

from common.models.document import IngestResult, ParsedDocument

from pipeline.ingestion.stages.chunker import chunk_document
from pipeline.ingestion.stages.metadata import generate_metadata
from pipeline.ingestion.stages.parser import PdfSource, DocxSource
from pipeline.ingestion.stages.storage import EmbedConsumer

logger = logging.getLogger(__name__)

# In-memory job store for SSE progress streaming.
# Maps job_id -> list of status strings.
_JOB_STORE: dict[str, list[str]] = {}
_JOB_DONE: dict[str, bool] = {}

_PDF_EXTENSIONS = frozenset({".pdf"})
_DOCX_EXTENSIONS = frozenset({".epub", ".docx"})


def _parse_document(
    file_path: str | Path, course_id: str, source_type: str,
) -> ParsedDocument:
    """Stage 1: Parse a document file into a ParsedDocument."""
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in _PDF_EXTENSIONS:
        return PdfSource().read(str(path), course_id, source_type)
    if ext in _DOCX_EXTENSIONS:
        return DocxSource().read(str(path), course_id, source_type)

    raise ValueError(
        f"Unsupported file extension: {ext!r}. "
        f"Supported: {sorted(_PDF_EXTENSIONS | _DOCX_EXTENSIONS)}"
    )


def ingest_document(document_key: str, course_id: str, source_type: str) -> None:
    """Entry point called by the worker for each RabbitMQ message.

    Runs the full 4-stage pipeline synchronously (wraps the async ingest function).
    """
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(ingest(document_key, course_id, source_type))
    finally:
        loop.close()


async def ingest(
    file_path: str | Path,
    course_id: str,
    source_type: str = "textbook",
    job_id: str | None = None,
    database_url: str | None = None,
    openai_api_key: str | None = None,
    anthropic_api_key: str | None = None,
    embedding_model: str | None = None,
) -> IngestResult:
    """Run the full four-stage ingestion pipeline.

    Parameters
    ----------
    file_path:
        Path to the source file (PDF, EPUB, or DOCX).
    course_id:
        Course identifier — used as the primary key in Postgres.
    source_type:
        One of textbook, slides, lecture_notes, exercises.
    job_id:
        If provided, progress events are written to ``_JOB_STORE[job_id]``
        and can be streamed via SSE.
    database_url / openai_api_key / anthropic_api_key / embedding_model:
        Override the corresponding env vars. Mainly used in tests.
    """
    jid = job_id or str(uuid.uuid4())
    _JOB_STORE[jid] = []
    _JOB_DONE[jid] = False

    def _emit(msg: str) -> None:
        logger.info(msg, extra={"job_id": jid, "course_id": course_id})
        _JOB_STORE.setdefault(jid, []).append(msg)

    embed_consumer = EmbedConsumer(
        database_url=database_url,
        openai_api_key=openai_api_key,
        embedding_model=embedding_model,
    )

    try:
        _emit("stage:1:start — Document Restructuring")
        doc: ParsedDocument = _parse_document(file_path, course_id, source_type)
        n_elements = sum(len(s.elements) for ch in doc.chapters for s in ch.sections)
        _emit(f"stage:1:done — {n_elements} elements")

        _emit("stage:2:start — Structure-Aware Chunking")
        chunks = chunk_document(doc)
        _emit(f"stage:2:done — {len(chunks)} chunks")

        _emit("stage:3:start — Metadata Generation")
        (
            enriched_chunks,
            section_summaries,
            chapter_summaries,
            course_summary,
        ) = await generate_metadata(
            chunks,
            doc,
            api_key=anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY"),
        )
        summaries_created = len(section_summaries) + len(chapter_summaries) + 1
        _emit(f"stage:3:done — {summaries_created} summaries")

        _emit("stage:4:start — Embedding and Storage")
        stored_count = await embed_consumer.run(
            doc=doc,
            chunks=enriched_chunks,
            section_summaries=section_summaries,
            chapter_summaries=chapter_summaries,
            course_summary=course_summary,
        )
        _emit(f"stage:4:done — {stored_count} chunks stored")

        _emit("done")
        return IngestResult(
            course_id=course_id,
            ingested_chunks=stored_count,
            summaries_created=summaries_created,
        )

    except Exception as exc:
        _emit(f"error:{exc!s}")
        raise
    finally:
        _JOB_DONE[jid] = True


async def job_events(job_id: str) -> AsyncIterator[str]:
    """Yield SSE-formatted progress strings for *job_id*."""
    seen = 0
    while True:
        events = _JOB_STORE.get(job_id, [])
        for msg in events[seen:]:
            yield f"data: {msg}\n\n"
            seen += 1
        if _JOB_DONE.get(job_id) and seen >= len(events):
            break
        await asyncio.sleep(0.2)


__all__ = ["ingest", "ingest_document", "job_events"]
