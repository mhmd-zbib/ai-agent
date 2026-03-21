"""
Pipeline stage events.

Stage 0 → Stage 1 : DocumentUploadedEvent  (defined in modules/documents)
Stage 1 → Stage 2 : ParsedEvent            (defined here)
Stage 2 → Stage 3 : ChunkEvent             (defined here, one per chunk)
Stage 3 → Stage 4 : EmbedEvent             (defined here, one per chunk)
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class ParsedEvent(BaseModel):
    """Published by the parse worker to chunk.queue after successful parsing."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: Literal["document.parsed"] = "document.parsed"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    document_id: str = Field(description="Postgres documents.document_id")
    upload_id: str
    user_id: str | None = None
    file_name: str
    content_type: str | None = None
    bucket: str
    object_prefix: str

    parsed_text_key: str = Field(
        description="MinIO object key of the saved .txt file (documents/{upload_id}/parsed.txt)"
    )
    parsed_pages_key: str | None = Field(
        default=None,
        description="MinIO object key of the pages JSON array (PDFs only; None for DOCX/TXT)",
    )
    total_pages: int | None = Field(
        default=None, description="Page count for PDFs; None otherwise"
    )


class ChunkEvent(BaseModel):
    """
    Published by the chunk worker to embed.queue — one message per text chunk.
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: Literal["document.chunked"] = "document.chunked"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    document_id: str
    upload_id: str
    user_id: str | None = None
    file_name: str
    content_type: str | None = None

    chunk_id: str = Field(description="Stable deterministic chunk identifier")
    chunk_index: int = Field(ge=0)
    chunk_text: str
    source_page: int | None = None
    total_chunks: int = Field(
        ge=1, description="Total number of chunks produced for this document"
    )


class EmbedEvent(BaseModel):
    """
    Published by the embed worker to store.queue — one message per chunk.
    Carries the embedding vector alongside all chunk metadata.
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: Literal["document.embedded"] = "document.embedded"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    document_id: str
    upload_id: str
    user_id: str | None = None
    file_name: str
    content_type: str | None = None

    chunk_id: str
    chunk_index: int = Field(ge=0)
    chunk_text: str
    source_page: int | None = None
    total_chunks: int = Field(ge=1)

    vector: list[float] = Field(description="Embedding vector")


class StoredEvent(BaseModel):
    """
    Emitted internally by the store worker after a successful Pinecone upsert.
    Not published to any queue — used for in-process signalling / logging.
    """

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: Literal["document.stored"] = "document.stored"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    document_id: str
    chunk_id: str
    chunk_index: int
    vector_id: str
    is_last_chunk: bool = Field(
        description="True when all chunks for the document have been stored"
    )
