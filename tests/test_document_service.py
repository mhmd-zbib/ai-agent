from io import BytesIO

from fastapi import UploadFile

from app.modules.documents.services.document_service import DocumentService


class _FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload_bytes(self, *, object_key: str, payload: bytes, content_type: str | None = None) -> None:  # noqa: ARG002
        self.objects[object_key] = payload


class _FakePublisher:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def publish_json(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


def test_upload_chunked_document_stores_chunks_and_publishes_event() -> None:
    storage = _FakeStorage()
    publisher = _FakePublisher()
    service = DocumentService(
        bucket_name="documents",
        default_chunk_size_bytes=4,
        storage=storage,
        event_publisher=publisher,
    )

    file = UploadFile(filename="hello.txt", file=BytesIO(b"abcdefghij"), headers={"content-type": "text/plain"})

    response = service.upload_chunked_document(file=file, user_id="user-1")

    assert response.chunk_count == 3
    assert response.total_size_bytes == 10
    assert response.bucket == "documents"
    assert response.event_published is True

    chunk_keys = sorted(k for k in storage.objects if "/chunks/" in k)
    assert len(chunk_keys) == 3
    assert storage.objects[chunk_keys[0]] == b"abcd"
    assert storage.objects[chunk_keys[1]] == b"efgh"
    assert storage.objects[chunk_keys[2]] == b"ij"

    assert response.manifest_key in storage.objects
    assert len(publisher.payloads) == 1
    event = publisher.payloads[0]
    assert event["event_type"] == "document.uploaded"
    assert event["upload_id"] == response.upload_id
    assert event["manifest_key"] == response.manifest_key


def test_upload_uses_explicit_chunk_size() -> None:
    storage = _FakeStorage()
    publisher = _FakePublisher()
    service = DocumentService(
        bucket_name="documents",
        default_chunk_size_bytes=10,
        storage=storage,
        event_publisher=publisher,
    )

    file = UploadFile(filename="small.txt", file=BytesIO(b"12345"), headers={"content-type": "text/plain"})

    response = service.upload_chunked_document(file=file, user_id="user-1", chunk_size_bytes=2)

    assert response.chunk_count == 3
    assert response.chunk_size_bytes == 2

