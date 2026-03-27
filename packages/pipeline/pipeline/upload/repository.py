"""Repository layer for document upload persistence.

Two ports are defined here:
  - IDocumentStorageRepository — MinIO operations (presigned URLs, manifest upload).
  - IDocumentRecordRepository  — Postgres document record CRUD.

Concrete implementations follow each protocol class.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Protocol

from shared.storage.minio import MinioStorageClient


# ---------------------------------------------------------------------------
# Storage port + adapter (MinIO)
# ---------------------------------------------------------------------------


class IDocumentStorageRepository(Protocol):
    """Port: object-storage operations needed during document upload."""

    def upload_bytes(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str | None = None,
    ) -> None:
        """Write *payload* to *object_key* in the configured bucket."""
        ...

    def presigned_put_url(self, *, object_key: str, expires: timedelta) -> str:
        """Return a presigned PUT URL for *object_key* valid for *expires*."""
        ...


class MinioDocumentStorageRepository:
    """Concrete adapter: delegates to MinioStorageClient."""

    def __init__(self, client: MinioStorageClient) -> None:
        self._client = client

    def upload_bytes(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str | None = None,
    ) -> None:
        self._client.upload_bytes(
            object_key=object_key,
            payload=payload,
            content_type=content_type,
        )

    def presigned_put_url(self, *, object_key: str, expires: timedelta) -> str:
        return self._client.presigned_put_url(object_key=object_key, expires=expires)


# ---------------------------------------------------------------------------
# Document record port + adapter (Postgres)
# ---------------------------------------------------------------------------


class IDocumentRecordRepository(Protocol):
    """Port: persist a document record to a relational database."""

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
        course_code: str,
        university_name: str,
    ) -> None:
        """Insert a new document row with status ``uploaded``."""
        ...


class PostgresDocumentRecordRepository:
    """Concrete adapter: writes document records via a raw SQLAlchemy engine.

    The table is assumed to already exist (managed by Alembic migrations).
    Schema (minimum columns used here):

        documents (
            document_id      TEXT PRIMARY KEY,
            upload_id        TEXT NOT NULL,
            user_id          TEXT,
            file_name        TEXT NOT NULL,
            content_type     TEXT,
            bucket           TEXT NOT NULL,
            object_prefix    TEXT NOT NULL,
            manifest_key     TEXT NOT NULL,
            upload_chunk_count INTEGER NOT NULL,
            total_size_bytes   BIGINT NOT NULL,
            course_code      TEXT NOT NULL,
            university_name  TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'uploaded',
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """

    def __init__(self, engine: object) -> None:
        # Accepts any SQLAlchemy Engine (sync).  Kept as ``object`` to avoid
        # importing sqlalchemy at module import time.
        self._engine = engine

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
        course_code: str,
        university_name: str,
    ) -> None:
        from sqlalchemy import text

        sql = text(
            """
            INSERT INTO documents (
                document_id, upload_id, user_id, file_name, content_type,
                bucket, object_prefix, manifest_key, upload_chunk_count,
                total_size_bytes, course_code, university_name, status
            ) VALUES (
                :document_id, :upload_id, :user_id, :file_name, :content_type,
                :bucket, :object_prefix, :manifest_key, :upload_chunk_count,
                :total_size_bytes, :course_code, :university_name, 'uploaded'
            )
            """
        )
        with self._engine.begin() as conn:  # type: ignore[attr-defined]
            conn.execute(
                sql,
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
                    "course_code": course_code,
                    "university_name": university_name,
                },
            )
