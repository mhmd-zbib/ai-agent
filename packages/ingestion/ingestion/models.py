"""Shared data models for the ingestion pipeline.

Backward compatibility shim — all types now live in ``shared.models.document``.
This module re-exports them unchanged so existing imports continue to work.

Local-only types (not in shared):
- HealthResponse — used only by the old FastAPI wrapper.
"""

from __future__ import annotations

# Backward compat — these types now live in shared.models.document
from shared.models.document import (
    ATOMIC_ELEMENT_TYPES,
    ELEMENT_TYPES,
    HEADING_ELEMENT_TYPES,
    Chapter,
    ChapterSummary,
    Chunk,
    ChunkMetadata,
    CourseSummary,
    DocumentElement,
    IngestRequest,
    IngestResult,
    ParsedDocument,
    Section,
    SectionSummary,
)

# Keep local-only type here — not part of shared models
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    db_connected: bool
    embedding_model: str


__all__ = [
    # re-exported from shared.models.document
    "ELEMENT_TYPES",
    "ATOMIC_ELEMENT_TYPES",
    "HEADING_ELEMENT_TYPES",
    "DocumentElement",
    "Section",
    "Chapter",
    "ParsedDocument",
    "Chunk",
    "ChunkMetadata",
    "SectionSummary",
    "ChapterSummary",
    "CourseSummary",
    "IngestRequest",
    "IngestResult",
    # local only
    "HealthResponse",
]
