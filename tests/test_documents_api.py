from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.documents.schemas import (
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadInitiateRequest,
    UploadInitiateResponse,
    ChunkUploadUrl,
)
from app.modules.users.schemas import UserOut
from app.shared import deps


class _FakeDocumentService:
    def __init__(self) -> None:
        self.initiate_calls: list[tuple[UploadInitiateRequest, str | None]] = []
        self.complete_calls: list[tuple[str, UploadCompleteRequest, str | None]] = []

    def initiate_upload(
        self,
        *,
        request: UploadInitiateRequest,
        user_id: str | None,
    ) -> UploadInitiateResponse:
        self.initiate_calls.append((request, user_id))
        chunk_count = 2
        return UploadInitiateResponse(
            upload_id="upload-1",
            bucket="documents",
            object_prefix="documents/upload-1",
            chunk_size_bytes=request.chunk_size_bytes or 1048576,
            chunk_count=chunk_count,
            chunks=[
                ChunkUploadUrl(
                    chunk_index=i,
                    object_key=f"documents/upload-1/chunks/{i:06d}",
                    presigned_url=f"https://minio.example.com/chunk-{i}",
                )
                for i in range(chunk_count)
            ],
        )

    def complete_upload(
        self,
        *,
        upload_id: str,
        request: UploadCompleteRequest,
        user_id: str | None,
    ) -> UploadCompleteResponse:
        self.complete_calls.append((upload_id, request, user_id))
        return UploadCompleteResponse(
            upload_id=upload_id,
            event_id="event-1",
            event_published=True,
        )


def test_initiate_upload_returns_presigned_urls() -> None:
    app = create_app()
    fake_service = _FakeDocumentService()

    app.dependency_overrides[deps.get_current_user] = lambda: UserOut(id="user-123", email="test@example.com")
    app.dependency_overrides[deps.get_document_service] = lambda: fake_service

    client = TestClient(app)

    response = client.post(
        "/v1/documents/uploads",
        json={
            "file_name": "report.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 2097152,
            "chunk_size_bytes": 1048576,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["upload_id"] == "upload-1"
    assert payload["chunk_count"] == 2
    assert len(payload["chunks"]) == 2
    assert payload["chunks"][0]["chunk_index"] == 0
    assert "presigned_url" in payload["chunks"][0]

    req, uid = fake_service.initiate_calls[0]
    assert req.file_name == "report.pdf"
    assert uid == "user-123"


def test_complete_upload_triggers_event() -> None:
    app = create_app()
    fake_service = _FakeDocumentService()

    app.dependency_overrides[deps.get_current_user] = lambda: UserOut(id="user-123", email="test@example.com")
    app.dependency_overrides[deps.get_document_service] = lambda: fake_service

    client = TestClient(app)

    response = client.post(
        "/v1/documents/uploads/upload-1/complete",
        json={
            "file_name": "report.pdf",
            "content_type": "application/pdf",
            "chunks": [
                {"chunk_index": 0, "size_bytes": 1048576},
                {"chunk_index": 1, "size_bytes": 524288},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["upload_id"] == "upload-1"
    assert payload["event_id"] == "event-1"
    assert payload["event_published"] is True

    upload_id, req, uid = fake_service.complete_calls[0]
    assert upload_id == "upload-1"
    assert len(req.chunks) == 2
    assert uid == "user-123"
