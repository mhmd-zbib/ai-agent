from fastapi.testclient import TestClient

from app.main import create_app
from app.shared.exceptions import AuthenticationError, ConflictError


class FakeUserService:
    def __init__(self) -> None:
        self._users: dict[str, dict[str, str]] = {}

    def register_user(self, payload):
        if payload.email in self._users:
            raise ConflictError("User with this email already exists.")

        user = {
            "id": "user-1",
            "email": payload.email,
            "university": payload.university.value,
            "major": payload.major.value,
        }
        self._users[payload.email] = {
            "id": user["id"],
            "password": payload.password,
            "university": payload.university.value,
            "major": payload.major.value,
        }
        return user

    def login(self, payload):
        stored = self._users.get(payload.email)
        if stored is None or stored["password"] != payload.password:
            raise AuthenticationError("Invalid email or password.")

        return {"access_token": "good-token", "token_type": "bearer"}

    def get_user_from_token(self, token: str):
        if token != "good-token":
            raise AuthenticationError("Invalid or expired token.")
        return {
            "id": "user-1",
            "email": "test@example.com",
            "university": "LIU",
            "major": "COMPUTER_SCIENCE",
        }

    def close(self) -> None:
        return


def test_register_and_login() -> None:
    app = create_app()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    register_response = client.post(
        "/v1/users/register",
        json={
            "email": "test@example.com",
            "password": "password123",
            "university": "LIU",
            "major": "COMPUTER_SCIENCE",
        },
    )
    assert register_response.status_code == 201
    body = register_response.json()
    assert body["email"] == "test@example.com"
    assert body["university"] == "LIU"
    assert body["major"] == "COMPUTER_SCIENCE"

    login_response = client.post(
        "/v1/users/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["access_token"] == "good-token"


def test_register_missing_university_returns_422() -> None:
    app = create_app()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    response = client.post(
        "/v1/users/register",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 422


def test_register_invalid_university_returns_422() -> None:
    app = create_app()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    response = client.post(
        "/v1/users/register",
        json={
            "email": "test@example.com",
            "password": "password123",
            "university": "INVALID",
            "major": "COMPUTER_SCIENCE",
        },
    )
    assert response.status_code == 422


def test_register_invalid_major_returns_422() -> None:
    app = create_app()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    response = client.post(
        "/v1/users/register",
        json={
            "email": "test@example.com",
            "password": "password123",
            "university": "LIU",
            "major": "INVALID_MAJOR",
        },
    )
    assert response.status_code == 422


def test_me_requires_token() -> None:
    app = create_app()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    response = client.get("/v1/users/me")
    assert response.status_code == 401


def test_me_with_token() -> None:
    app = create_app()
    app.state.user_service = FakeUserService()
    client = TestClient(app)

    response = client.get(
        "/v1/users/me",
        headers={"Authorization": "Bearer good-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": "user-1",
        "email": "test@example.com",
        "university": "LIU",
        "major": "COMPUTER_SCIENCE",
    }
