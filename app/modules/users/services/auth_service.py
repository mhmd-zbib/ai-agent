from datetime import UTC, datetime, timedelta

import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext

from app.modules.users.schemas.response import TokenResponse
from app.shared.exceptions import AuthenticationError, ConfigurationError


class AuthService:
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def __init__(
        self,
        secret_key: str,
        algorithm: str,
        access_token_expire_minutes: int,
    ) -> None:
        if not secret_key:
            raise ConfigurationError("JWT_SECRET_KEY is required.")

        self._secret_key = secret_key
        self._algorithm = algorithm
        self._access_token_expire_minutes = access_token_expire_minutes

    def hash_password(self, password: str) -> str:
        return self._pwd_context.hash(password)

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        return self._pwd_context.verify(plain_password, password_hash)

    def create_token(self, user_id: str) -> TokenResponse:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self._access_token_expire_minutes)
        payload = {
            "sub": user_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(payload, self._secret_key, algorithm=self._algorithm)
        return TokenResponse(access_token=token)

    def decode_subject(self, token: str) -> str:
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
            )
        except InvalidTokenError as exc:
            raise AuthenticationError("Invalid or expired token.") from exc

        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise AuthenticationError("Invalid or expired token.")

        return subject
