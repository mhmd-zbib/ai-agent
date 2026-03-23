from datetime import datetime, UTC
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.modules.users.schemas import UserOut
from app.shared.exceptions import AuthenticationError


class FakeChatService:
    def __init__(self) -> None:
        self._history: dict[str, list[dict[str, str]]] = {}

    def create_session(self, course_code: str = ""):
        session_id = str(uuid4())
        self._history.setdefault(session_id, [])
        return {"session_id": session_id}

    def reply(self, payload, user_id: str = "", university_name="LIU"):
        history = self._history.setdefault(payload.session_id, [])
        history.append({"role": "user", "content": payload.question})
        reply = f"echo: {payload.question}"
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
            },
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
        return UserOut(
            id="user-1",
            email="test@example.com",
            university="LIU",
            major="COMPUTER_SCIENCE",
        )


class FakeToolActionChatService(FakeChatService):
    def reply(self, payload, user_id: str = "", university_name="LIU"):
        response = super().reply(
            payload, user_id=user_id, university_name=university_name
        )
        response["tool_action"] = {"tool_id": "weather", "params": {"city": "Beirut"}}
        return response


def test_chat_roundtrip() -> None:
    app = create_app()
    app.state.chat_service = FakeChatService()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    session_response = client.post(
        "/v1/agent/sessions",
        json={"course_code": "CS101"},
        headers={"Authorization": "Bearer good-token"},
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["session_id"]

    first = client.post(
        "/v1/agent/chat",
        json={"session_id": session_id, "question": "hello"},
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
        json={"session_id": session_id, "question": "how are you?"},
        headers={"Authorization": "Bearer good-token"},
    )
    assert second.status_code == 200
    second_json = second.json()
    assert second_json["session_id"] == session_id
    assert second_json["content"] == "echo: how are you?"


def test_chat_hides_tool_action_when_service_returns_it() -> None:
    app = create_app()
    app.state.chat_service = FakeToolActionChatService()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    session_response = client.post(
        "/v1/agent/sessions",
        json={"course_code": "CS101"},
        headers={"Authorization": "Bearer good-token"},
    )
    session_id = session_response.json()["session_id"]

    response = client.post(
        "/v1/agent/chat",
        json={"session_id": session_id, "question": "hello"},
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 200
    assert "tool_action" not in response.json()


def test_reset_session() -> None:
    app = create_app()
    app.state.chat_service = FakeChatService()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    session_response = client.post(
        "/v1/agent/sessions",
        json={"course_code": "CS101"},
        headers={"Authorization": "Bearer good-token"},
    )
    session_id = session_response.json()["session_id"]

    client.post(
        "/v1/agent/chat",
        json={"session_id": session_id, "question": "hello"},
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

    response = client.post(
        "/v1/agent/chat",
        json={"session_id": "s1", "question": "hello"},
    )
    assert response.status_code == 401
