"""Unit tests for UploadService."""

from __future__ import annotations

import json

import pytest

from shared.enums import University

from pipeline.upload.schemas import ChunkInfo, UploadCompleteRequest, UploadInitiateRequest
from pipeline.upload.service import UploadService


# ---------------------------------------------------------------------------
# initiate_upload
# ---------------------------------------------------------------------------


def test_initiate_upload_returns_correct_chunk_count(
    upload_service: UploadService,
    fake_storage: object,
) -> None:
    request = UploadInitiateRequest(
        file_name="lecture1.pdf",
        file_size_bytes=15 * 1024 * 1024,  # 15 MiB
    )
    # Default chunk size is 5 MiB → expect 3 chunks
    response = upload_service.initiate_upload(request=request, user_id=None)

    assert response.chunk_count == 3
    assert len(response.chunks) == 3
    assert response.bucket == "test-bucket"


def test_initiate_upload_uses_custom_chunk_size(
    upload_service: UploadService,
) -> None:
    request = UploadInitiateRequest(
        file_name="doc.pdf",
        file_size_bytes=10 * 1024 * 1024,
        chunk_size_bytes=2 * 1024 * 1024,  # 2 MiB → 5 chunks
    )
    response = upload_service.initiate_upload(request=request, user_id=None)
    assert response.chunk_count == 5
    assert response.chunk_size_bytes == 2 * 1024 * 1024


def test_initiate_upload_chunk_indices_are_sequential(
    upload_service: UploadService,
) -> None:
    request = UploadInitiateRequest(file_name="f.pdf", file_size_bytes=6 * 1024 * 1024)
    response = upload_service.initiate_upload(request=request, user_id="user-1")
    indices = [c.chunk_index for c in response.chunks]
    assert indices == list(range(len(indices)))


def test_initiate_upload_generates_presigned_urls(
    upload_service: UploadService,
    fake_storage: object,  # actually FakeStorageRepository
) -> None:
    from tests.conftest import FakeStorageRepository

    assert isinstance(fake_storage, FakeStorageRepository)

    request = UploadInitiateRequest(file_name="doc.pdf", file_size_bytes=5 * 1024 * 1024)
    response = upload_service.initiate_upload(request=request, user_id=None)

    assert all("presigned=1" in c.presigned_url for c in response.chunks)
    assert len(fake_storage.presigned_calls) == response.chunk_count


def test_initiate_upload_object_keys_use_upload_id(
    upload_service: UploadService,
) -> None:
    request = UploadInitiateRequest(file_name="doc.pdf", file_size_bytes=5 * 1024 * 1024)
    response = upload_service.initiate_upload(request=request, user_id=None)

    upload_id = response.upload_id
    for chunk in response.chunks:
        assert chunk.object_key.startswith(f"documents/{upload_id}/chunks/")


# ---------------------------------------------------------------------------
# complete_upload
# ---------------------------------------------------------------------------


def _make_complete_request(chunk_count: int = 2) -> UploadCompleteRequest:
    return UploadCompleteRequest(
        file_name="lecture1.pdf",
        content_type="application/pdf",
        chunks=[ChunkInfo(chunk_index=i, size_bytes=1024) for i in range(chunk_count)],
        course_code="CS101",
        university_name=University.LIU,
    )


def test_complete_upload_publishes_event(
    upload_service: UploadService,
    fake_publisher: object,
) -> None:
    from tests.conftest import FakePublisher

    assert isinstance(fake_publisher, FakePublisher)

    response = upload_service.complete_upload(
        upload_id="test-upload-id",
        request=_make_complete_request(),
        user_id="user-1",
    )

    assert response.event_published is True
    assert len(fake_publisher.published) == 1
    event = fake_publisher.published[0]
    assert event["event_type"] == "document.uploaded"
    assert event["upload_id"] == "test-upload-id"
    assert event["user_id"] == "user-1"
    assert event["course_code"] == "CS101"


def test_complete_upload_writes_manifest_to_storage(
    upload_service: UploadService,
    fake_storage: object,
) -> None:
    from tests.conftest import FakeStorageRepository

    assert isinstance(fake_storage, FakeStorageRepository)

    upload_service.complete_upload(
        upload_id="uid-abc",
        request=_make_complete_request(chunk_count=3),
        user_id=None,
    )

    manifest_uploads = [u for u in fake_storage.uploaded if "manifest.json" in u["object_key"]]
    assert len(manifest_uploads) == 1

    manifest = json.loads(manifest_uploads[0]["payload"])
    assert manifest["upload_id"] == "uid-abc"
    assert manifest["chunk_count"] == 3


def test_complete_upload_creates_document_record(
    upload_service: UploadService,
    fake_record_repo: object,
) -> None:
    from tests.conftest import FakeRecordRepository

    assert isinstance(fake_record_repo, FakeRecordRepository)

    upload_service.complete_upload(
        upload_id="uid-xyz",
        request=_make_complete_request(),
        user_id="user-42",
    )

    assert len(fake_record_repo.created) == 1
    record = fake_record_repo.created[0]
    assert record["upload_id"] == "uid-xyz"
    assert record["user_id"] == "user-42"
    assert record["course_code"] == "CS101"


def test_complete_upload_response_fields(upload_service: UploadService) -> None:
    response = upload_service.complete_upload(
        upload_id="uid-resp",
        request=_make_complete_request(),
        user_id=None,
    )
    assert response.upload_id == "uid-resp"
    assert response.document_id
    assert response.event_id
    assert response.event_published is True
