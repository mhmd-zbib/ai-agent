"""Pipeline FastAPI application.

Exposes:
  POST /ingest               — run the full ingestion pipeline
  GET  /ingest/status/{id}   — stream progress via Server-Sent Events
  GET  /health               — DB connectivity + embedding model
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from ingestion.models import HealthResponse, IngestResult
from ingestion.orchestrator import ingest, job_events

_EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-large")
_DATABASE_URL = os.environ.get("DATABASE_URL", "")


# ──────────────────────────────────────────────────────────────────────────────
# App factory
# ──────────────────────────────────────────────────────────────────────────────


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield  # nothing to start/stop for the pipeline app


def create_app() -> FastAPI:
    return FastAPI(
        title="Course AI Tutor — Ingestion Pipeline",
        description="Ingests raw course books into a hybrid Postgres + pgvector database.",
        version="1.0.0",
        lifespan=_lifespan,
    )


app = create_app()


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────


@app.post(
    "/ingest",
    summary="Ingest a course document",
    description=(
        "Upload a PDF, EPUB, or DOCX file. Runs Stages 1–4 and returns "
        "the number of chunks and summaries created. "
        "Use GET /ingest/status/{job_id} to stream progress."
    ),
    response_model=IngestResult,
    status_code=status.HTTP_200_OK,
)
async def ingest_document(
    course_id: str = Form(..., description="Course identifier, e.g. CS101"),
    source_type: str = Form(
        default="textbook", description="textbook|slides|lecture_notes|exercises"
    ),
    file: UploadFile = File(..., description="PDF, EPUB, or DOCX file"),  # noqa: B008
) -> IngestResult:
    _validate_source_type(source_type)
    _validate_file_type(file.filename or "")

    job_id = str(uuid.uuid4())

    suffix = Path(file.filename or "upload.pdf").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = await ingest(
            file_path=tmp_path,
            course_id=course_id,
            source_type=source_type,
            job_id=job_id,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return result


@app.get(
    "/ingest/status/{job_id}",
    summary="Stream ingestion progress",
    description=(
        "Server-Sent Events stream of progress messages for a running or completed job."
    ),
    status_code=status.HTTP_200_OK,
)
async def ingest_status(job_id: str) -> StreamingResponse:
    return StreamingResponse(
        job_events(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get(
    "/health",
    summary="Health check",
    description="Returns database connectivity status and the embedding model in use.",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
)
async def health() -> HealthResponse:
    db_ok = await _check_db()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db_connected=db_ok,
        embedding_model=_EMBEDDING_MODEL,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _validate_source_type(source_type: str) -> None:
    valid = {"textbook", "slides", "lecture_notes", "exercises"}
    if source_type not in valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"source_type must be one of {sorted(valid)}",
        )


def _validate_file_type(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in {".pdf", ".epub", ".docx"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported file type {ext!r}. Supported: .pdf, .epub, .docx",
        )


async def _check_db() -> bool:
    if not _DATABASE_URL:
        return False
    try:
        conn = await asyncpg.connect(_DATABASE_URL)
        await conn.execute("SELECT 1")
        await conn.close()
        return True
    except Exception:  # noqa: BLE001
        return False


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
