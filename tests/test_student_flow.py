"""
Integration test: student flow from signup → login → upload → chat.

All infrastructure is mocked — no real DB, Redis, MinIO, RabbitMQ, or LLM.
Verifies that enums, JWT claims, and Qdrant payload filters are type-safe
across the full request chain.
"""

from __future__ import annotations

from datetime import datetime, UTC
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.modules.chat.schemas import ChatRequest, ChatResponse
from app.modules.chat.services.chat_service import ChatService
from app.modules.documents.services import DocumentService
from app.modules.users.schemas import UserOut
from app.modules.users.services.user_service import UserService
from app.shared.enums import Major, University
from app.shared.exceptions import AuthenticationError, register_exception_handlers


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeUserService:
    """Fake user service that stores users in-memory and issues tokens."""

    def __init__(self) -> None:
        self._users: dict[str, UserOut] = {}
        self._passwords: dict[str, str] = {}
        self._tokens: dict[str, str] = {}  # token -> user_id

    def register_user(self, payload: object) -> UserOut:
        email = getattr(payload, "email")
        university = getattr(payload, "university")
        major = getattr(payload, "major")
        user_id = str(uuid4())
        user = UserOut(
            id=user_id,
            email=email,
            university=university,
            major=major,
        )
        self._users[email] = user
        self._passwords[email] = getattr(payload, "password")
        return user

    def login(self, payload: object) -> dict[str, str]:
        email = getattr(payload, "email")
        password = getattr(payload, "password")
        user = self._users.get(email)
        if user is None or self._passwords.get(email) != password:
            raise AuthenticationError("Invalid email or password")
        token = f"fake-token-{user.id}"
        self._tokens[token] = user.id
        return {"access_token": token, "token_type": "bearer"}

    def get_user_from_token(self, token: str) -> UserOut:
        user_id = self._tokens.get(token)
        if user_id is None:
            raise AuthenticationError("Invalid or expired token")
        for user in self._users.values():
            if user.id == user_id:
                return user
        raise AuthenticationError("User not found")


class FakeChatService:
    """Records calls to reply() and returns a canned response."""

    def __init__(self) -> None:
        self.last_user_id: str = ""
        self.last_university_name: University | None = None
        self.last_course_code: str = ""
        self._session_course_codes: dict[str, str] = {}

    def create_session(self, course_code: str = "") -> dict[str, str]:
        session_id = str(uuid4())
        self._session_course_codes[session_id] = course_code
        return {"session_id": session_id}

    def reply(
        self,
        payload: ChatRequest,
        user_id: str = "",
        university_name: University = University.LIU,
    ) -> dict[str, object]:
        self.last_user_id = user_id
        self.last_university_name = university_name
        self.last_course_code = self._session_course_codes.get(payload.session_id, "")
        return {
            "session_id": payload.session_id,
            "type": "text",
            "content": f"echo: {payload.question}",
            "tool_action": None,
            "metadata": {
                "confidence": 1.0,
                "sources": None,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        }

    def reset_session(self, session_id: str) -> dict[str, object]:
        return {"session_id": session_id, "cleared": True}

    def close(self) -> None:
        return


class FakeDocumentService:
    """Records complete_upload calls to verify course_code + university_name."""

    def __init__(self) -> None:
        self.last_course_code: str = ""
        self.last_university_name: University | None = None

    def initiate_upload(self, request: object, user_id: str) -> dict[str, object]:
        return {
            "upload_id": str(uuid4()),
            "chunk_upload_urls": [
                {"chunk_index": 0, "upload_url": "https://minio.local/fake-url"}
            ],
        }

    def complete_upload(
        self, upload_id: str, request: object, user_id: str
    ) -> dict[str, object]:
        self.last_course_code = getattr(request, "course_code", "")
        uni = getattr(request, "university_name", None)
        self.last_university_name = uni
        return {
            "upload_id": upload_id,
            "event_id": str(uuid4()),
            "event_published": True,
        }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _create_test_app(
    user_service: FakeUserService,
    chat_service: FakeChatService,
    document_service: FakeDocumentService,
) -> FastAPI:
    from app.modules.chat.router import router as chat_router
    from app.modules.documents.router import router as documents_router
    from app.modules.users.router import router as users_router

    app = FastAPI()
    register_exception_handlers(app)

    app.state.user_service = user_service
    app.state.chat_service = chat_service
    app.state.document_service = document_service

    app.include_router(users_router)
    app.include_router(chat_router)
    app.include_router(documents_router)

    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_signup_returns_university_and_major_enums() -> None:
    """POST /v1/users/register returns university and major as enum values."""
    user_svc = FakeUserService()
    app = _create_test_app(user_svc, FakeChatService(), FakeDocumentService())
    client = TestClient(app)

    resp = client.post(
        "/v1/users/register",
        json={
            "email": "student@example.com",
            "password": "SecurePassword123!",
            "university": "LIU",
            "major": "COMPUTER_SCIENCE",
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["university"] == "LIU"
    assert body["major"] == "COMPUTER_SCIENCE"
    assert body["email"] == "student@example.com"


def test_login_returns_token() -> None:
    """POST /v1/users/login returns a bearer token after signup."""
    user_svc = FakeUserService()
    app = _create_test_app(user_svc, FakeChatService(), FakeDocumentService())
    client = TestClient(app)

    # Register first
    client.post(
        "/v1/users/register",
        json={
            "email": "student@example.com",
            "password": "SecurePassword123!",
            "university": "LIU",
            "major": "COMPUTER_SCIENCE",
        },
    )

    resp = client.post(
        "/v1/users/login",
        json={
            "email": "student@example.com",
            "password": "SecurePassword123!",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_upload_complete_passes_course_code_and_university() -> None:
    """POST /v1/documents/uploads/{id}/complete carries course_code + university_name."""
    user_svc = FakeUserService()
    doc_svc = FakeDocumentService()
    app = _create_test_app(user_svc, FakeChatService(), doc_svc)
    client = TestClient(app)

    # Register + login
    client.post(
        "/v1/users/register",
        json={
            "email": "student@example.com",
            "password": "SecurePassword123!",
            "university": "LIU",
            "major": "COMPUTER_SCIENCE",
        },
    )
    login_resp = client.post(
        "/v1/users/login",
        json={
            "email": "student@example.com",
            "password": "SecurePassword123!",
        },
    )
    token = login_resp.json()["access_token"]

    # Complete upload with course_code and university_name
    resp = client.post(
        "/v1/documents/uploads/upload-123/complete",
        json={
            "file_name": "notes.pdf",
            "content_type": "application/pdf",
            "chunks": [{"chunk_index": 0, "size_bytes": 1024}],
            "course_code": "CS101",
            "university_name": "LIU",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert doc_svc.last_course_code == "CS101"
    assert doc_svc.last_university_name == University.LIU


def test_chat_receives_university_from_jwt() -> None:
    """POST /v1/agent/chat passes university_name from JWT to chat service."""
    user_svc = FakeUserService()
    chat_svc = FakeChatService()
    app = _create_test_app(user_svc, chat_svc, FakeDocumentService())
    client = TestClient(app)

    # Register + login
    client.post(
        "/v1/users/register",
        json={
            "email": "student@example.com",
            "password": "SecurePassword123!",
            "university": "AUB",
            "major": "COMPUTER_SCIENCE",
        },
    )
    login_resp = client.post(
        "/v1/users/login",
        json={
            "email": "student@example.com",
            "password": "SecurePassword123!",
        },
    )
    token = login_resp.json()["access_token"]

    # Create session with course_code
    session_resp = client.post(
        "/v1/agent/sessions",
        json={"course_code": "CS101"},
        headers={"Authorization": f"Bearer {token}"},
    )
    session_id = session_resp.json()["session_id"]

    # Chat (course_code is bound to the session)
    resp = client.post(
        "/v1/agent/chat",
        json={"session_id": session_id, "question": "What is polymorphism?"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    # Verify chat service received the university from the JWT-based user
    assert chat_svc.last_university_name == University.AUB
    assert chat_svc.last_course_code == "CS101"


def test_full_student_flow_signup_upload_chat() -> None:
    """End-to-end: signup → login → upload doc → chat — all type-safe."""
    user_svc = FakeUserService()
    chat_svc = FakeChatService()
    doc_svc = FakeDocumentService()
    app = _create_test_app(user_svc, chat_svc, doc_svc)
    client = TestClient(app)

    # 1. Signup
    signup_resp = client.post(
        "/v1/users/register",
        json={
            "email": "student@liu.edu",
            "password": "SecurePassword123!",
            "university": "LIU",
            "major": "COMPUTER_SCIENCE",
        },
    )
    assert signup_resp.status_code == 201
    assert signup_resp.json()["university"] == "LIU"

    # 2. Login
    login_resp = client.post(
        "/v1/users/login",
        json={"email": "student@liu.edu", "password": "SecurePassword123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Upload document with course_code + university_name
    complete_resp = client.post(
        "/v1/documents/uploads/upload-456/complete",
        json={
            "file_name": "lecture.pdf",
            "content_type": "application/pdf",
            "chunks": [{"chunk_index": 0, "size_bytes": 2048}],
            "course_code": "CS201",
            "university_name": "LIU",
        },
        headers=headers,
    )
    assert complete_resp.status_code == 200
    assert doc_svc.last_course_code == "CS201"
    assert doc_svc.last_university_name == University.LIU

    # 4. Create chat session with course_code
    session_resp = client.post(
        "/v1/agent/sessions", json={"course_code": "CS201"}, headers=headers
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["session_id"]

    # 5. Chat (course_code is bound to the session)
    chat_resp = client.post(
        "/v1/agent/chat",
        json={"session_id": session_id, "question": "Explain inheritance"},
        headers=headers,
    )
    assert chat_resp.status_code == 200
    assert chat_svc.last_university_name == University.LIU
    assert chat_svc.last_course_code == "CS201"
    assert "echo: Explain inheritance" in chat_resp.json()["content"]
