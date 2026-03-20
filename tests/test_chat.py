from datetime import datetime, UTC
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.shared.exceptions import AuthenticationError


class FakeChatService:
    def __init__(self) -> None:
        self._history: dict[str, list[dict[str, str]]] = {}

    def create_session(self):
        session_id = str(uuid4())
        self._history.setdefault(session_id, [])
        return {"session_id": session_id}

    def reply(self, payload):
        history = self._history.setdefault(payload.session_id, [])
        history.append({"role": "user", "content": payload.message})
        reply = f"echo: {payload.message}"
        history.append({"role": "assistant", "content": reply})
        return {
            "session_id": payload.session_id,
            "type": "text",
            "content": reply,
            "tool_action": None,
            "metadata": {
                "confidence": 1.0,
                "sources": None,
                "timestamp": datetime.now(UTC).isoformat(),
            }
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

    session_response = client.post(
        "/v1/agent/sessions",
        headers={"Authorization": "Bearer good-token"},
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    first = client.post(
        "/v1/agent/chat",
        json={"session_id": session_id, "message": "hello"},
        headers={"Authorization": "Bearer good-token"},
    )
    assert first.status_code == 200
    first_json = first.json()
    assert first_json["content"] == "echo: hello"
    assert first_json["session_id"] == session_id
    assert first_json["type"] == "text"
    assert "tool_action" not in first_json
    assert "metadata" in first_json
    assert "history" not in first_json

    second = client.post(
        "/v1/agent/chat",
        json={"session_id": session_id, "message": "how are you?"},
        headers={"Authorization": "Bearer good-token"},
    )
    assert second.status_code == 200
    second_json = second.json()
    assert second_json["session_id"] == session_id
    assert second_json["content"] == "echo: how are you?"


def test_reset_session() -> None:
    app = create_app()
    app.state.chat_service = FakeChatService()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    session_response = client.post(
        "/v1/agent/sessions",
        headers={"Authorization": "Bearer good-token"},
    )
    session_id = session_response.json()["session_id"]

    client.post(
        "/v1/agent/chat",
        json={"session_id": session_id, "message": "hello"},
        headers={"Authorization": "Bearer good-token"},
    )
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

    response = client.post("/v1/agent/chat", json={"session_id": "s1", "message": "hello"})
    assert response.status_code == 401
