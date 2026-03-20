from io import BytesIO

from fastapi import UploadFile
from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.documents.schemas import DocumentUploadResponse
from app.modules.users.schemas import UserOut
from app.shared import deps


class _FakeDocumentService:
    def __init__(self) -> None:
        self.last_file_name: str | None = None
        self.last_user_id: str | None = None
        self.last_chunk_size: int | None = None

    def upload_chunked_document(
        self,
        *,
        file: UploadFile,
        user_id: str | None,
        chunk_size_bytes: int | None = None,
    ) -> DocumentUploadResponse:
        self.last_file_name = file.filename
        self.last_user_id = user_id
        self.last_chunk_size = chunk_size_bytes

        return DocumentUploadResponse(
            upload_id="upload-1",
            bucket="documents",
            object_prefix="documents/upload-1",
            manifest_key="documents/upload-1/manifest.json",
            chunk_size_bytes=chunk_size_bytes or 1024,
            chunk_count=1,
            total_size_bytes=5,
            event_id="event-1",
            event_published=True,
        )


def test_upload_documents_endpoint_uses_authenticated_user_and_payload() -> None:
    app = create_app()
    fake_service = _FakeDocumentService()

    app.dependency_overrides[deps.get_current_user] = lambda: UserOut(id="user-123", email="test@example.com")
    app.dependency_overrides[deps.get_document_service] = lambda: fake_service

    client = TestClient(app)

    response = client.post(
        "/v1/documents/uploads",
        files={"file": ("note.txt", BytesIO(b"hello"), "text/plain")},
        data={"chunk_size_bytes": "2048"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["upload_id"] == "upload-1"
    assert payload["chunk_size_bytes"] == 2048

    assert fake_service.last_file_name == "note.txt"
    assert fake_service.last_user_id == "user-123"
    assert fake_service.last_chunk_size == 2048
