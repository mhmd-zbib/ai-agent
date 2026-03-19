from fastapi.testclient import TestClient

from app.main import create_app
from app.shared.exceptions import AuthenticationError


class FakeChatService:
    def __init__(self) -> None:
        self._history: dict[str, list[dict[str, str]]] = {}

    def reply(self, payload):
        session_id = payload.session_id or "test-session"
        history = self._history.setdefault(session_id, [])
        history.append({"role": "user", "content": payload.message})
        reply = f"echo: {payload.message}"
        history.append({"role": "assistant", "content": reply})
        return {
            "session_id": session_id,
            "reply": reply,
            "history": [
                {
                    "role": item["role"],
                    "content": item["content"],
                    "created_at": "2026-01-01T00:00:00+00:00",
                }
                for item in history
            ],
        }

    def reset_session(self, session_id: str):
        existed = session_id in self._history
        self._history.pop(session_id, None)
        return {"session_id": session_id, "cleared": existed}

    def close(self) -> None:
        return


class FakeUserService:
    def get_user_from_token(self, token: str):
        if token != "good-token":
            raise AuthenticationError("Invalid or expired token.")
        return {"id": "user-1", "email": "test@example.com"}


def test_chat_roundtrip() -> None:
    app = create_app()
    app.state.chat_service = FakeChatService()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    first = client.post(
        "/v1/agent/chat",
        json={"message": "hello"},
        headers={"Authorization": "Bearer good-token"},
    )
    assert first.status_code == 200
    first_json = first.json()
    assert first_json["reply"] == "echo: hello"
    session_id = first_json["session_id"]
    assert session_id
    assert len(first_json["history"]) == 2

    second = client.post(
        "/v1/agent/chat",
        json={"session_id": session_id, "message": "how are you?"},
        headers={"Authorization": "Bearer good-token"},
    )
    assert second.status_code == 200
    second_json = second.json()
    assert second_json["session_id"] == session_id
    assert len(second_json["history"]) == 4


def test_reset_session() -> None:
    app = create_app()
    app.state.chat_service = FakeChatService()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    first = client.post(
        "/v1/agent/chat",
        json={"message": "hello"},
        headers={"Authorization": "Bearer good-token"},
    )
    session_id = first.json()["session_id"]
    response = client.delete(
        f"/v1/agent/sessions/{session_id}",
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"session_id": session_id, "cleared": True}


def test_chat_requires_auth() -> None:
    app = create_app()
    app.state.chat_service = FakeChatService()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    response = client.post("/v1/agent/chat", json={"message": "hello"})
    assert response.status_code == 401
