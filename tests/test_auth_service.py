from app.modules.users.config import AuthConfig
from app.modules.users.services.auth_service import AuthService


def _make_service() -> AuthService:
    return AuthService(
        config=AuthConfig(
            secret_key="test-secret",
            algorithm="HS256",
            access_token_expire_minutes=60,
        )
    )


def test_hash_and_verify_password_long_ascii() -> None:
    service = _make_service()
    long_password = "a" * 200

    password_hash = service.hash_password(long_password)

    assert service.verify_password(long_password, password_hash)
    assert not service.verify_password("wrong-password", password_hash)


def test_hash_and_verify_password_long_multibyte() -> None:
    service = _make_service()
    long_password = "\U0001f642" * 100

    password_hash = service.hash_password(long_password)

    assert service.verify_password(long_password, password_hash)


def test_create_token_includes_university_and_major() -> None:
    service = _make_service()

    token_response = service.create_token("user-123", "LIU", "COMPUTER_SCIENCE")

    assert token_response.access_token
    claims = service.decode_token(token_response.access_token)
    assert claims.user_id == "user-123"
    assert claims.university == "LIU"
    assert claims.major == "COMPUTER_SCIENCE"


def test_decode_token_returns_claims() -> None:
    service = _make_service()

    token_response = service.create_token("user-456", "AUB", "COMPUTER_SCIENCE")
    claims = service.decode_token(token_response.access_token)

    assert claims.user_id == "user-456"
    assert claims.university == "AUB"
    assert claims.major == "COMPUTER_SCIENCE"
