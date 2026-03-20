import json
from uuid import uuid4

from fastapi import UploadFile

from app.modules.documents.repositories.document_event_repository import IDocumentEventRepository
from app.modules.documents.repositories.document_storage_repository import IDocumentStorageRepository
from app.modules.documents.schemas import DocumentUploadResponse, DocumentUploadedEvent
from app.shared.exceptions import UpstreamServiceError


class DocumentService:
    def __init__(
        self,
        *,
        bucket_name: str,
        default_chunk_size_bytes: int,
        storage: IDocumentStorageRepository,
        event_publisher: IDocumentEventRepository,
    ) -> None:
        self._bucket_name = bucket_name
        self._default_chunk_size_bytes = default_chunk_size_bytes
        self._storage = storage
        self._event_publisher = event_publisher

    @property
    def default_chunk_size_bytes(self) -> int:
        return self._default_chunk_size_bytes

    def upload_chunked_document(
        self,
        *,
        file: UploadFile,
        user_id: str | None,
        chunk_size_bytes: int | None = None,
    ) -> DocumentUploadResponse:
        chunk_size = chunk_size_bytes or self._default_chunk_size_bytes
        if chunk_size <= 0:
            raise ValueError("chunk_size_bytes must be greater than zero")

        upload_id = str(uuid4())
        object_prefix = f"documents/{upload_id}"
        manifest_key = f"{object_prefix}/manifest.json"

        file.file.seek(0)
        chunk_keys: list[str] = []
        total_size = 0
        chunk_index = 0

        while True:
            chunk = file.file.read(chunk_size)
            if not chunk:
                break

            total_size += len(chunk)
            chunk_key = f"{object_prefix}/chunks/{chunk_index:06d}"
            chunk_index += 1
            chunk_keys.append(chunk_key)

            self._storage.upload_bytes(
                object_key=chunk_key,
                payload=chunk,
                content_type="application/octet-stream",
            )

        manifest = {
            "upload_id": upload_id,
            "file_name": file.filename or "uploaded-document",
            "content_type": file.content_type,
            "chunk_count": len(chunk_keys),
            "total_size_bytes": total_size,
            "chunk_keys": chunk_keys,
        }
        self._storage.upload_bytes(
            object_key=manifest_key,
            payload=json.dumps(manifest).encode("utf-8"),
            content_type="application/json",
        )

        event = DocumentUploadedEvent(
            event_id=str(uuid4()),
            upload_id=upload_id,
            user_id=user_id,
            file_name=file.filename or "uploaded-document",
            content_type=file.content_type,
            bucket=self._bucket_name,
            object_prefix=object_prefix,
            manifest_key=manifest_key,
            chunk_keys=chunk_keys,
            chunk_size_bytes=chunk_size,
            chunk_count=len(chunk_keys),
            total_size_bytes=total_size,
        )

        try:
            self._event_publisher.publish_json(event.model_dump(mode="json"))
        except Exception as exc:  # pragma: no cover - defensive around broker libs
            raise UpstreamServiceError("Failed to publish document upload event") from exc

        return DocumentUploadResponse(
            upload_id=upload_id,
            bucket=self._bucket_name,
            object_prefix=object_prefix,
            manifest_key=manifest_key,
            chunk_size_bytes=chunk_size,
            chunk_count=len(chunk_keys),
            total_size_bytes=total_size,
            event_id=event.event_id,
            event_published=True,
        )

    def close(self) -> None:
        return
