from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.main import create_app
from app.shared.exceptions import AuthenticationError


class FakeUserService:
    def get_user_from_token(self, token: str):
        if token != "good-token":
            raise AuthenticationError("Invalid or expired token.")
        return {"id": "user-1", "email": "test@example.com"}


class FakeChatService:
    def create_session(self):
        return {"session_id": "session-1"}

    def reply(self, payload):
        return {"session_id": payload.session_id, "reply": "ok"}

    def reset_session(self, session_id: str):
        return {"session_id": session_id, "cleared": True}

    def close(self) -> None:
        return


def test_unhandled_exception_response_is_sanitized() -> None:
    app = create_app()
    app.state.user_service = FakeUserService()
    app.state.chat_service = FakeChatService()

    router = APIRouter()

    @router.get("/_test/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("sensitive internals")

    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/_test/boom", headers={"x-request-id": "req-123"})

    assert response.status_code == 500
    assert response.headers.get("x-request-id") == "req-123"
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "An unexpected error occurred.",
            "request_id": "req-123",
        }
    }


def test_validation_error_has_clean_response_shape() -> None:
    app = create_app()
    app.state.user_service = FakeUserService()
    app.state.chat_service = FakeChatService()
    client = TestClient(app)

    response = client.post(
        "/v1/agent/chat",
        json={"session_id": "session-1"},
        headers={"Authorization": "Bearer good-token", "x-request-id": "req-456"},
    )

    assert response.status_code == 422
    assert response.headers.get("x-request-id") == "req-456"
    assert response.json() == {
        "error": {
            "code": "validation_error",
            "message": "Invalid request payload.",
            "request_id": "req-456",
        }
    }
