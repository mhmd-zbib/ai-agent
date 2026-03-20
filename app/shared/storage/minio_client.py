from io import BytesIO
from threading import Lock

from minio import Minio


class MinioStorageClient:
    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        secure: bool,
    ) -> None:
        self._bucket_name = bucket_name
        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._bucket_lock = Lock()
        self._bucket_ready = False

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return

        with self._bucket_lock:
            if self._bucket_ready:
                return

            if not self._client.bucket_exists(self._bucket_name):
                self._client.make_bucket(self._bucket_name)

            self._bucket_ready = True

    def upload_bytes(self, *, object_key: str, payload: bytes, content_type: str | None = None) -> None:
        self._ensure_bucket()
        stream = BytesIO(payload)
        self._client.put_object(
            self._bucket_name,
            object_key,
            stream,
            length=len(payload),
            content_type=content_type,
        )

    def close(self) -> None:
        return

