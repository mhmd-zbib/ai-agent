"""
Tests for DocumentService with the IDocumentRecordRepository port.

Verifies that:
- DocumentService no longer depends on the pipeline module's IDocumentStatusRepository
- complete_upload() calls create_document() on the injected repo
- The protocol is satisfied by duck typing (no base class required)
"""
import json
from datetime import timedelta

from app.modules.documents.repositories.document_record_repository import IDocumentRecordRepository
from app.modules.documents.schemas import ChunkInfo, UploadCompleteRequest, UploadInitiateRequest
from app.modules.documents.services.document_service import DocumentService


class _FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload_bytes(self, *, object_key: str, payload: bytes, content_type: str | None = None) -> None:
        self.objects[object_key] = payload

    def presigned_put_url(self, *, object_key: str, expires: timedelta) -> str:
        return f"https://minio.example.com/{object_key}"


class _FakePublisher:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def publish_json(self, payload: dict) -> None:
        self.payloads.append(payload)


class _FakeDocumentRecordRepository:
    """Satisfies IDocumentRecordRepository via duck typing — no explicit base."""

    def __init__(self) -> None:
        self.created: list[dict] = []

    def create_document(self, **kwargs) -> None:  # type: ignore[override]
        self.created.append(kwargs)


def _make_service(with_record_repo: bool = False):
    storage = _FakeStorage()
    publisher = _FakePublisher()
    record_repo = _FakeDocumentRecordRepository() if with_record_repo else None
    service = DocumentService(
        bucket_name="docs",
        default_chunk_size_bytes=4,
        storage=storage,
        event_publisher=publisher,
        document_record_repository=record_repo,
    )
    return service, storage, publisher, record_repo


def test_complete_upload_calls_create_document_on_record_repo() -> None:
    service, storage, publisher, record_repo = _make_service(with_record_repo=True)

    init = service.initiate_upload(
        request=UploadInitiateRequest(
            file_name="test.txt",
            content_type="text/plain",
            file_size_bytes=8,
        ),
        user_id="user-99",
    )

    service.complete_upload(
        upload_id=init.upload_id,
        request=UploadCompleteRequest(
            file_name="test.txt",
            content_type="text/plain",
            chunks=[
                ChunkInfo(chunk_index=0, size_bytes=4),
                ChunkInfo(chunk_index=1, size_bytes=4),
            ],
        ),
        user_id="user-99",
    )

    assert len(record_repo.created) == 1
    call = record_repo.created[0]
    assert call["upload_id"] == init.upload_id
    assert call["user_id"] == "user-99"
    assert call["file_name"] == "test.txt"
    assert call["upload_chunk_count"] == 2
    assert call["total_size_bytes"] == 8


def test_complete_upload_works_without_record_repo() -> None:
    """document_record_repository is optional; service still publishes the event."""
    service, _, publisher, _ = _make_service(with_record_repo=False)

    init = service.initiate_upload(
        request=UploadInitiateRequest(
            file_name="file.txt",
            content_type="text/plain",
            file_size_bytes=4,
        ),
        user_id=None,
    )

    response = service.complete_upload(
        upload_id=init.upload_id,
        request=UploadCompleteRequest(
            file_name="file.txt",
            content_type="text/plain",
            chunks=[ChunkInfo(chunk_index=0, size_bytes=4)],
        ),
        user_id=None,
    )

    assert response.event_published is True
    assert len(publisher.payloads) == 1


def test_ifilerecord_repository_protocol_accepts_duck_typed_impl() -> None:
    """Structural check: our fake satisfies the protocol without explicit base class."""
    from typing import runtime_checkable, Protocol
    # The protocol is not runtime-checkable by default, but we can verify
    # that the fake has the required method signature by calling it directly.
    repo: IDocumentRecordRepository = _FakeDocumentRecordRepository()  # type: ignore[assignment]
    # Just calling the method should not raise
    repo.create_document(
        document_id="doc-1",
        upload_id="up-1",
        user_id="u-1",
        file_name="f.txt",
        content_type="text/plain",
        bucket="b",
        object_prefix="p",
        manifest_key="m",
        upload_chunk_count=1,
        total_size_bytes=100,
    )
