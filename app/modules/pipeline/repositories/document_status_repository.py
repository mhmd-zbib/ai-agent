"""
Postgres-backed repository for RAG pipeline document status tracking.

Schema
------
documents
    document_id   — UUID, PK (Python-generated)
    upload_id     — unique, links back to the upload flow
    user_id       — nullable
    file_name
    content_type  — nullable MIME type
    bucket        — MinIO bucket
    object_prefix — MinIO key prefix
    manifest_key  — MinIO key of the manifest JSON
    upload_chunk_count — number of upload chunks (not RAG chunks)
    total_size_bytes
    status        — see DocumentStatus enum
    error_message — populated on failure
    created_at
    updated_at

document_chunks
    chunk_id      — deterministic string (document_id + chunk index)
    document_id   — FK → documents.document_id
    chunk_index
    source_page   — nullable
    vector_id     — Pinecone vector ID (same as chunk_id)
    stored_at     — timestamptz, set when upserted to Pinecone
"""

from typing import Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.shared.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

class DocumentStatus:
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    CHUNKING = "chunking"
    CHUNKED = "chunked"
    EMBEDDING = "embedding"
    STORING = "storing"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class IDocumentStatusRepository(Protocol):
    def ensure_schema(self) -> None: ...

    def create_document(
        self,
        *,
        document_id: str,
        upload_id: str,
        user_id: str | None,
        file_name: str,
        content_type: str | None,
        bucket: str,
        object_prefix: str,
        manifest_key: str,
        upload_chunk_count: int,
        total_size_bytes: int,
    ) -> None: ...

    def update_status(self, *, document_id: str, status: str) -> None: ...

    def update_status_conditional(
        self, *, document_id: str, new_status: str, from_status: str
    ) -> None: ...

    def update_status_failed(self, *, document_id: str, error_message: str) -> None: ...

    def update_total_chunks(self, *, document_id: str, total_chunks: int) -> None: ...

    def record_chunk_stored(
        self,
        *,
        document_id: str,
        chunk_id: str,
        chunk_index: int,
        source_page: int | None,
        vector_id: str,
    ) -> None: ...

    def count_stored_chunks(self, *, document_id: str) -> int: ...


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------

class DocumentStatusRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS documents (
                        document_id   VARCHAR(64)  PRIMARY KEY,
                        upload_id     VARCHAR(64)  NOT NULL UNIQUE,
                        user_id       VARCHAR(128),
                        file_name     TEXT         NOT NULL,
                        content_type  VARCHAR(128),
                        bucket        VARCHAR(128) NOT NULL,
                        object_prefix TEXT         NOT NULL,
                        manifest_key  TEXT         NOT NULL,
                        upload_chunk_count INTEGER  NOT NULL DEFAULT 0,
                        total_size_bytes   BIGINT   NOT NULL DEFAULT 0,
                        status        VARCHAR(32)  NOT NULL DEFAULT 'uploaded',
                        error_message TEXT,
                        created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                        updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS document_chunks (
                        chunk_id      TEXT        PRIMARY KEY,
                        document_id   VARCHAR(64) NOT NULL
                            REFERENCES documents(document_id) ON DELETE CASCADE,
                        chunk_index   INTEGER     NOT NULL,
                        source_page   INTEGER,
                        vector_id     TEXT,
                        stored_at     TIMESTAMPTZ
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
                    ON document_chunks (document_id)
                    """
                )
            )
            # Idempotent migration: add total_chunks column if it doesn't exist yet
            conn.execute(
                text(
                    "ALTER TABLE documents ADD COLUMN IF NOT EXISTS total_chunks INTEGER"
                )
            )

    def create_document(
        self,
        *,
        document_id: str,
        upload_id: str,
        user_id: str | None,
        file_name: str,
        content_type: str | None,
        bucket: str,
        object_prefix: str,
        manifest_key: str,
        upload_chunk_count: int,
        total_size_bytes: int,
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO documents (
                        document_id, upload_id, user_id, file_name, content_type,
                        bucket, object_prefix, manifest_key,
                        upload_chunk_count, total_size_bytes, status
                    ) VALUES (
                        :document_id, :upload_id, :user_id, :file_name, :content_type,
                        :bucket, :object_prefix, :manifest_key,
                        :upload_chunk_count, :total_size_bytes, 'uploaded'
                    )
                    ON CONFLICT (upload_id) DO NOTHING
                    """
                ),
                {
                    "document_id": document_id,
                    "upload_id": upload_id,
                    "user_id": user_id,
                    "file_name": file_name,
                    "content_type": content_type,
                    "bucket": bucket,
                    "object_prefix": object_prefix,
                    "manifest_key": manifest_key,
                    "upload_chunk_count": upload_chunk_count,
                    "total_size_bytes": total_size_bytes,
                },
            )

    def update_status(self, *, document_id: str, status: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE documents
                    SET status = :status, updated_at = NOW()
                    WHERE document_id = :document_id
                    """
                ),
                {"document_id": document_id, "status": status},
            )
        logger.info(
            "Document status updated",
            extra={"document_id": document_id, "status": status},
        )

    def update_status_conditional(
        self, *, document_id: str, new_status: str, from_status: str
    ) -> None:
        """Update status only if the current status matches *from_status* (atomic guard)."""
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE documents
                    SET status = :new_status, updated_at = NOW()
                    WHERE document_id = :document_id
                      AND status = :from_status
                    """
                ),
                {
                    "document_id": document_id,
                    "new_status": new_status,
                    "from_status": from_status,
                },
            )
        logger.info(
            "Document status conditionally updated",
            extra={
                "document_id": document_id,
                "new_status": new_status,
                "from_status": from_status,
            },
        )

    def update_total_chunks(self, *, document_id: str, total_chunks: int) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE documents
                    SET total_chunks = :total_chunks, updated_at = NOW()
                    WHERE document_id = :document_id
                    """
                ),
                {"document_id": document_id, "total_chunks": total_chunks},
            )

    def update_status_failed(self, *, document_id: str, error_message: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE documents
                    SET status = 'failed', error_message = :error_message,
                        updated_at = NOW()
                    WHERE document_id = :document_id
                    """
                ),
                {"document_id": document_id, "error_message": error_message},
            )
        logger.error(
            "Document marked as failed",
            extra={"document_id": document_id, "error": error_message},
        )

    def record_chunk_stored(
        self,
        *,
        document_id: str,
        chunk_id: str,
        chunk_index: int,
        source_page: int | None,
        vector_id: str,
    ) -> None:
        from datetime import UTC, datetime

        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO document_chunks
                        (chunk_id, document_id, chunk_index, source_page,
                         vector_id, stored_at)
                    VALUES
                        (:chunk_id, :document_id, :chunk_index, :source_page,
                         :vector_id, :stored_at)
                    ON CONFLICT (chunk_id) DO UPDATE
                        SET vector_id = EXCLUDED.vector_id,
                            stored_at = EXCLUDED.stored_at
                    """
                ),
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "chunk_index": chunk_index,
                    "source_page": source_page,
                    "vector_id": vector_id,
                    "stored_at": datetime.now(UTC),
                },
            )

    def count_stored_chunks(self, *, document_id: str) -> int:
        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM document_chunks
                    WHERE document_id = :document_id
                      AND stored_at IS NOT NULL
                    """
                ),
                {"document_id": document_id},
            ).scalar_one()
            return int(result)
