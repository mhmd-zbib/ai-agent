import json
import math
from datetime import timedelta
from uuid import uuid4

from app.modules.documents.repositories.document_event_repository import (
    IDocumentEventRepository,
)
from app.modules.documents.repositories.document_storage_repository import (
    IDocumentStorageRepository,
)
from app.modules.documents.schemas import (
    ChunkInfo,
    ChunkUploadUrl,
    DocumentUploadedEvent,
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadInitiateRequest,
    UploadInitiateResponse,
)
from app.modules.documents.repositories.document_record_repository import (
    IDocumentRecordRepository,
)
from app.shared.exceptions import UpstreamServiceError

_PRESIGNED_URL_EXPIRY = timedelta(hours=1)


class DocumentService:
    def __init__(
        self,
        *,
        bucket_name: str,
        default_chunk_size_bytes: int,
        storage: IDocumentStorageRepository,
        event_publisher: IDocumentEventRepository,
        document_record_repository: IDocumentRecordRepository | None = None,
    ) -> None:
        self._bucket_name = bucket_name
        self._default_chunk_size_bytes = default_chunk_size_bytes
        self._storage = storage
        self._event_publisher = event_publisher
        self._status_repo = document_record_repository

    @property
    def default_chunk_size_bytes(self) -> int:
        return self._default_chunk_size_bytes

    def initiate_upload(
        self,
        *,
        request: UploadInitiateRequest,
        user_id: str | None,
    ) -> UploadInitiateResponse:
        """
        Phase 1: Generate presigned PUT URLs for each chunk.

        The client uploads chunks directly to MinIO using these URLs,
        bypassing the backend entirely. Call complete_upload when done.
        """
        chunk_size = request.chunk_size_bytes or self._default_chunk_size_bytes
        upload_id = str(uuid4())
        object_prefix = f"documents/{upload_id}"

        chunk_count = math.ceil(request.file_size_bytes / chunk_size)

        chunks = []
        for i in range(chunk_count):
            object_key = f"{object_prefix}/chunks/{i:06d}"
            url = self._storage.presigned_put_url(
                object_key=object_key,
                expires=_PRESIGNED_URL_EXPIRY,
            )
            chunks.append(
                ChunkUploadUrl(chunk_index=i, object_key=object_key, presigned_url=url)
            )

        return UploadInitiateResponse(
            upload_id=upload_id,
            bucket=self._bucket_name,
            object_prefix=object_prefix,
            chunk_size_bytes=chunk_size,
            chunk_count=chunk_count,
            chunks=chunks,
        )

    def complete_upload(
        self,
        *,
        upload_id: str,
        request: UploadCompleteRequest,
        user_id: str | None,
    ) -> UploadCompleteResponse:
        """
        Phase 2: Client has uploaded all chunks directly to MinIO.

        Write the manifest, create a Postgres document record (status=uploaded),
        and publish the processing event to the fanout exchange.
        """
        object_prefix = f"documents/{upload_id}"
        manifest_key = f"{object_prefix}/manifest.json"

        chunks_by_index: dict[int, ChunkInfo] = {
            c.chunk_index: c for c in request.chunks
        }
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

        # Create Postgres document record (status = uploaded)
        if self._status_repo is not None:
            self._status_repo.create_document(
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
            )

        event = DocumentUploadedEvent(
            event_id=str(uuid4()),
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

        try:
            self._event_publisher.publish_json(event.model_dump(mode="json"))
        except Exception as exc:  # pragma: no cover - defensive around broker libs
            raise UpstreamServiceError(
                "Failed to publish document upload event"
            ) from exc

        return UploadCompleteResponse(
            upload_id=upload_id,
            event_id=event.event_id,
            event_published=True,
        )

    def close(self) -> None:
        return
