import json
from datetime import timedelta

from app.modules.documents.schemas import (
    UploadCompleteRequest,
    UploadInitiateRequest,
    ChunkInfo,
)
from app.modules.documents.services.document_service import DocumentService
from app.shared.enums import University


class _FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.presigned_calls: list[str] = []

    def upload_bytes(
        self, *, object_key: str, payload: bytes, content_type: str | None = None
    ) -> None:  # noqa: ARG002
        self.objects[object_key] = payload

    def presigned_put_url(self, *, object_key: str, expires: timedelta) -> str:  # noqa: ARG002
        self.presigned_calls.append(object_key)
        return f"https://minio.example.com/{object_key}?presigned=1"


class _FakePublisher:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def publish_json(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


def _make_service(
    chunk_size: int = 4,
) -> tuple[DocumentService, _FakeStorage, _FakePublisher]:
    storage = _FakeStorage()
    publisher = _FakePublisher()
    service = DocumentService(
        bucket_name="documents",
        default_chunk_size_bytes=chunk_size,
        storage=storage,
        event_publisher=publisher,
    )
    return service, storage, publisher


def test_initiate_upload_generates_presigned_urls_per_chunk() -> None:
    service, storage, _ = _make_service(chunk_size=4)

    response = service.initiate_upload(
        request=UploadInitiateRequest(
            file_name="hello.txt",
            content_type="text/plain",
            file_size_bytes=10,  # 10 bytes / 4 = 3 chunks
        ),
        user_id="user-1",
    )

    assert response.chunk_count == 3
    assert response.chunk_size_bytes == 4
    assert response.bucket == "documents"
    assert len(response.chunks) == 3
    assert all(c.presigned_url.startswith("https://") for c in response.chunks)
    assert storage.presigned_calls == [c.object_key for c in response.chunks]


def test_initiate_upload_uses_explicit_chunk_size() -> None:
    service, _, _ = _make_service(chunk_size=1048576)

    response = service.initiate_upload(
        request=UploadInitiateRequest(
            file_name="small.txt",
            content_type="text/plain",
            file_size_bytes=5,
            chunk_size_bytes=2,  # override: 5 bytes / 2 = 3 chunks
        ),
        user_id="user-1",
    )

    assert response.chunk_count == 3
    assert response.chunk_size_bytes == 2


def test_complete_upload_writes_manifest_and_publishes_event() -> None:
    service, storage, publisher = _make_service(chunk_size=4)

    # First initiate to get upload_id
    init = service.initiate_upload(
        request=UploadInitiateRequest(
            file_name="hello.txt",
            content_type="text/plain",
            file_size_bytes=10,
        ),
        user_id="user-1",
    )

    # Then complete
    response = service.complete_upload(
        upload_id=init.upload_id,
        request=UploadCompleteRequest(
            file_name="hello.txt",
            content_type="text/plain",
            chunks=[
                ChunkInfo(chunk_index=0, size_bytes=4),
                ChunkInfo(chunk_index=1, size_bytes=4),
                ChunkInfo(chunk_index=2, size_bytes=2),
            ],
            course_code="CSC101",
            university_name=University.LIU,
        ),
        user_id="user-1",
    )

    assert response.upload_id == init.upload_id
    assert response.event_published is True

    # Manifest was written to storage
    assert init.object_prefix + "/manifest.json" in storage.objects
    manifest = json.loads(storage.objects[init.object_prefix + "/manifest.json"])
    assert manifest["chunk_count"] == 3
    assert manifest["total_size_bytes"] == 10
    assert len(manifest["chunk_keys"]) == 3

    # Event was published
    assert len(publisher.payloads) == 1
    event = publisher.payloads[0]
    assert event["event_type"] == "document.uploaded"
    assert event["upload_id"] == init.upload_id
    assert event["manifest_key"] == init.object_prefix + "/manifest.json"
    assert event["chunk_count"] == 3
    assert event["total_size_bytes"] == 10
    assert event["course_code"] == "CSC101"
    assert event["university_name"] == "LIU"
