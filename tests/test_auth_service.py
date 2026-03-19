from app.modules.users.services.auth_service import AuthService


def test_hash_and_verify_password_long_ascii() -> None:
    service = AuthService(
        secret_key="test-secret",
        algorithm="HS256",
        access_token_expire_minutes=60,
    )
    long_password = "a" * 200

    password_hash = service.hash_password(long_password)

    assert service.verify_password(long_password, password_hash)
    assert not service.verify_password("wrong-password", password_hash)


def test_hash_and_verify_password_long_multibyte() -> None:
    service = AuthService(
        secret_key="test-secret",
        algorithm="HS256",
        access_token_expire_minutes=60,
    )
    long_password = "🙂" * 100

    password_hash = service.hash_password(long_password)

    assert service.verify_password(long_password, password_hash)

