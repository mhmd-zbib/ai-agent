from datetime import timedelta
from typing import Protocol

from app.infrastructure.storage.minio import MinioStorageClient


class IDocumentStorageRepository(Protocol):
    def upload_bytes(
        self, *, object_key: str, payload: bytes, content_type: str | None = None
    ) -> None: ...
    def presigned_put_url(self, *, object_key: str, expires: timedelta) -> str: ...


class MinioDocumentStorageRepository:
    def __init__(self, client: MinioStorageClient) -> None:
        self._client = client

    def upload_bytes(
        self, *, object_key: str, payload: bytes, content_type: str | None = None
    ) -> None:
        self._client.upload_bytes(
            object_key=object_key, payload=payload, content_type=content_type
        )

    def presigned_put_url(self, *, object_key: str, expires: timedelta) -> str:
        return self._client.presigned_put_url(object_key=object_key, expires=expires)
