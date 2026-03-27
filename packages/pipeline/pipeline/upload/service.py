"""Upload business logic — initiate and complete multipart document uploads.

Flow:
  1. initiate_upload()  — generate presigned PUT URLs for every chunk.
  2. complete_upload()  — client has pushed all chunks; write manifest to MinIO,
                          create a Postgres document record, and publish a
                          DocumentUploadedEvent to the RabbitMQ fanout exchange.
"""

from __future__ import annotations

import json
import math
from datetime import timedelta
from uuid import uuid4

from shared.logging import get_logger
from shared.messaging.rabbitmq import RabbitMQPublisher

from pipeline.upload.repository import IDocumentRecordRepository, IDocumentStorageRepository
from pipeline.upload.schemas import (
    ChunkInfo,
    ChunkUploadUrl,
    DocumentUploadedEvent,
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadInitiateRequest,
    UploadInitiateResponse,
)

logger = get_logger(__name__)

_PRESIGNED_URL_EXPIRY = timedelta(hours=1)
_DEFAULT_CHUNK_SIZE_BYTES = 10 * 1024 * 1024  # 10 MiB


class UploadService:
    """Orchestrates multipart document upload initiation and completion."""

    def __init__(
        self,
        *,
        bucket_name: str,
        default_chunk_size_bytes: int = _DEFAULT_CHUNK_SIZE_BYTES,
        storage: IDocumentStorageRepository,
        publisher: RabbitMQPublisher,
        document_record_repository: IDocumentRecordRepository | None = None,
    ) -> None:
        self._bucket_name = bucket_name
        self._default_chunk_size_bytes = default_chunk_size_bytes
        self._storage = storage
        self._publisher = publisher
        self._record_repo = document_record_repository

    @property
    def default_chunk_size_bytes(self) -> int:
        return self._default_chunk_size_bytes

    # ------------------------------------------------------------------
    # Phase 1 — generate presigned PUT URLs
    # ------------------------------------------------------------------

    def initiate_upload(
        self,
        *,
        request: UploadInitiateRequest,
        user_id: str | None,
    ) -> UploadInitiateResponse:
        """Generate presigned PUT URLs — one per chunk.

        The client uploads each chunk directly to MinIO and then calls
        complete_upload() once all chunks have been transferred.
        """
        chunk_size = request.chunk_size_bytes or self._default_chunk_size_bytes
        upload_id = str(uuid4())
        object_prefix = f"documents/{upload_id}"

        chunk_count = math.ceil(request.file_size_bytes / chunk_size)

        chunks: list[ChunkUploadUrl] = []
        for i in range(chunk_count):
            object_key = f"{object_prefix}/chunks/{i:06d}"
            url = self._storage.presigned_put_url(
                object_key=object_key,
                expires=_PRESIGNED_URL_EXPIRY,
            )
            chunks.append(
                ChunkUploadUrl(chunk_index=i, object_key=object_key, presigned_url=url)
            )

        logger.info(
            "Upload initiated",
            extra={
                "upload_id": upload_id,
                "chunk_count": chunk_count,
                "file_name": request.file_name,
                "user_id": user_id,
            },
        )
        return UploadInitiateResponse(
            upload_id=upload_id,
            bucket=self._bucket_name,
            object_prefix=object_prefix,
            chunk_size_bytes=chunk_size,
            chunk_count=chunk_count,
            chunks=chunks,
        )

    # ------------------------------------------------------------------
    # Phase 2 — confirm all chunks uploaded; publish event
    # ------------------------------------------------------------------

    def complete_upload(
        self,
        *,
        upload_id: str,
        request: UploadCompleteRequest,
        user_id: str | None,
    ) -> UploadCompleteResponse:
        """Finalize upload: write manifest, create document record, publish event.

        Steps:
          1. Build manifest JSON from client-provided chunk metadata.
          2. Write manifest to MinIO so pipeline workers can locate chunks.
          3. Insert a Postgres document record (status = 'uploaded').
          4. Publish a ``DocumentUploadedEvent`` to the fanout exchange.
        """
        object_prefix = f"documents/{upload_id}"
        manifest_key = f"{object_prefix}/manifest.json"

        chunks_by_index: dict[int, ChunkInfo] = {c.chunk_index: c for c in request.chunks}
        chunk_count = len(chunks_by_index)
        total_size_bytes = sum(c.size_bytes for c in request.chunks)
        chunk_keys = [
            f"{object_prefix}/chunks/{i:06d}" for i in sorted(chunks_by_index)
        ]

        manifest = {
            "upload_id": upload_id,
            "file_name": request.file_name,
            "content_type": request.content_type,
            "chunk_count": chunk_count,
            "total_size_bytes": total_size_bytes,
            "chunk_keys": chunk_keys,
        }
        self._storage.upload_bytes(
            object_key=manifest_key,
            payload=json.dumps(manifest).encode("utf-8"),
            content_type="application/json",
        )

        document_id = str(uuid4())
        event_id = str(uuid4())

        if self._record_repo is not None:
            self._record_repo.create_document(
                document_id=document_id,
                upload_id=upload_id,
                user_id=user_id,
                file_name=request.file_name,
                content_type=request.content_type,
                bucket=self._bucket_name,
                object_prefix=object_prefix,
                manifest_key=manifest_key,
                upload_chunk_count=chunk_count,
                total_size_bytes=total_size_bytes,
                course_code=request.course_code,
                university_name=str(request.university_name),
            )

        event = DocumentUploadedEvent(
            event_id=event_id,
            document_id=document_id,
            upload_id=upload_id,
            user_id=user_id,
            file_name=request.file_name,
            content_type=request.content_type,
            bucket=self._bucket_name,
            object_prefix=object_prefix,
            manifest_key=manifest_key,
            chunk_count=chunk_count,
            total_size_bytes=total_size_bytes,
            course_code=request.course_code,
            university_name=request.university_name,
        )

        self._publisher.publish_json(event.model_dump(mode="json"))

        logger.info(
            "Upload completed and event published",
            extra={
                "upload_id": upload_id,
                "document_id": document_id,
                "event_id": event_id,
                "chunk_count": chunk_count,
                "total_size_bytes": total_size_bytes,
                "user_id": user_id,
            },
        )

        return UploadCompleteResponse(
            upload_id=upload_id,
            document_id=document_id,
            event_id=event_id,
            event_published=True,
        )
