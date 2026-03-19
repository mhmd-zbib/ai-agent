from datetime import UTC, datetime, timedelta
import hashlib

import bcrypt
import jwt
from jwt import InvalidTokenError

from app.modules.users.schemas.response import TokenResponse
from app.shared.exceptions import AuthenticationError, ConfigurationError


class AuthService:
    # Pre-hash passwords so bcrypt always receives fixed-size input (<72 bytes).
    @staticmethod
    def _prehash_password(password: str) -> bytes:
        return hashlib.sha256(password.encode("utf-8")).digest()

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
        prehashed = self._prehash_password(password)
        return bcrypt.hashpw(prehashed, bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        prehashed = self._prehash_password(plain_password)
        try:
            return bcrypt.checkpw(prehashed, password_hash.encode("utf-8"))
        except ValueError:
            return False

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
