"""
Tests confirming ParseService and ChunkService depend on IFileStorage, not MinioStorageClient.

Uses a plain fake object (no inheritance from MinioStorageClient) to prove
the dependency is satisfied by duck typing alone.
"""

import json
from datetime import timedelta

from app.shared.enums import University
from app.shared.protocols import IFileStorage
from app.modules.documents.schemas.events import DocumentUploadedEvent
from app.modules.pipeline.schemas.events import ParsedEvent
from app.modules.pipeline.services.chunk_service import ChunkService
from app.modules.pipeline.services.parse_service import ParseService


# ---------------------------------------------------------------------------
# Fake IFileStorage — does NOT inherit from MinioStorageClient
# ---------------------------------------------------------------------------


class _FakeStorage:
    """In-memory object store that satisfies IFileStorage by duck typing."""

    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self._objects: dict[str, bytes] = objects or {}
        self.uploaded: dict[str, bytes] = {}

    def upload_bytes(self, object_key: str, payload: bytes, content_type: str) -> None:
        self.uploaded[object_key] = payload
        self._objects[object_key] = payload

    def download_bytes(self, object_key: str) -> bytes:
        return self._objects[object_key]

    def presigned_put_url(self, object_key: str, expires: timedelta) -> str:
        return f"https://fake-storage/{object_key}"


# ---------------------------------------------------------------------------
# Fake status repo
# ---------------------------------------------------------------------------


class _FakeStatusRepo:
    def update_status(self, *, document_id: str, status: str) -> None:
        pass

    def update_status_failed(self, *, document_id: str, error_message: str) -> None:
        pass

    def update_total_chunks(self, *, document_id: str, total_chunks: int) -> None:
        pass

    def update_status_conditional(
        self, *, document_id: str, new_status: str, from_status: str
    ) -> None:
        pass


# ---------------------------------------------------------------------------
# ParseService tests
# ---------------------------------------------------------------------------


def test_parse_service_accepts_ifile_storage_duck_type() -> None:
    """ParseService works with any object satisfying IFileStorage (no concrete class)."""
    manifest = json.dumps(
        {
            "upload_id": "up-1",
            "file_name": "hello.txt",
            "content_type": "text/plain",
            "chunk_count": 1,
            "total_size_bytes": 5,
            "chunk_keys": ["documents/up-1/chunks/000000"],
        }
    ).encode()

    file_bytes = b"hello"

    storage = _FakeStorage(
        {
            "documents/up-1/manifest.json": manifest,
            "documents/up-1/chunks/000000": file_bytes,
        }
    )

    service = ParseService(storage=storage, status_repository=_FakeStatusRepo())

    event = DocumentUploadedEvent(
        event_id="ev-1",
        document_id="doc-1",
        upload_id="up-1",
        user_id="u-1",
        file_name="hello.txt",
        content_type="text/plain",
        bucket="docs",
        object_prefix="documents/up-1",
        manifest_key="documents/up-1/manifest.json",
        chunk_count=1,
        total_size_bytes=5,
        course_code="CSC101",
        university_name=University.LIU,
    )

    result = service.process(event)

    assert result.document_id == "doc-1"
    assert result.parsed_text_key == "documents/up-1/parsed.txt"
    # Parsed text was uploaded back to fake storage
    assert "documents/up-1/parsed.txt" in storage.uploaded
    assert storage.uploaded["documents/up-1/parsed.txt"].decode() == "hello"


def test_chunk_service_accepts_ifile_storage_duck_type() -> None:
    """ChunkService works with any object satisfying IFileStorage (no concrete class)."""
    text = "word1 word2 word3"
    storage = _FakeStorage({"parsed/text.txt": text.encode()})

    service = ChunkService(
        storage=storage,
        status_repository=_FakeStatusRepo(),
        window_tokens=10,
        overlap_tokens=0,
    )

    event = ParsedEvent(
        document_id="doc-2",
        upload_id="up-2",
        user_id="u-2",
        file_name="doc.txt",
        content_type="text/plain",
        bucket="docs",
        object_prefix="parsed",
        parsed_text_key="parsed/text.txt",
        parsed_pages_key=None,
        total_pages=None,
        course_code="CSC101",
        university_name=University.LIU,
    )

    chunks = service.process(event)

    assert len(chunks) >= 1
    assert all(c.document_id == "doc-2" for c in chunks)


def test_ifile_storage_protocol_interface() -> None:
    """Structural check: the protocol has the expected method signatures."""
    storage: IFileStorage = _FakeStorage()
    storage.upload_bytes("key", b"data", "application/octet-stream")
    data = storage.download_bytes("key")
    assert data == b"data"
    url = storage.presigned_put_url("key", timedelta(hours=1))
    assert "key" in url
