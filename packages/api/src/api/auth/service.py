"""Authentication service — JWT token management and password hashing."""

import hashlib
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Final

import bcrypt
import jwt
from api.auth.config import AuthConfig
from api.auth.schemas import TokenResponse
from common.core.exceptions import AuthenticationError
from jwt import InvalidTokenError


class TokenClaims:
    """Decoded JWT claims — minimal identity payload."""

    __slots__ = ("user_id", "role")

    def __init__(self, user_id: str, role: str) -> None:
        self.user_id = user_id
        self.role = role


class IAuthService(ABC):
    """Interface for authentication services (DIP)."""

    @abstractmethod
    def hash_password(self, password: str) -> str: ...

    @abstractmethod
    def verify_password(self, plain_password: str, password_hash: str) -> bool: ...

    @abstractmethod
    def create_token(self, user_id: str, role: str) -> TokenResponse: ...

    @abstractmethod
    def decode_token(self, token: str) -> TokenClaims: ...


class AuthService(IAuthService):
    """
    Authentication service implementing JWT token management and password hashing.
    Uses bcrypt with SHA256 pre-hashing for secure password storage.
    """

    _CLAIM_SUBJECT: Final[str] = "sub"
    _CLAIM_ISSUED_AT: Final[str] = "iat"
    _CLAIM_EXPIRATION: Final[str] = "exp"
    _CLAIM_ROLE: Final[str] = "role"

    _ERROR_INVALID_TOKEN: Final[str] = "Invalid or expired token"
    _ERROR_MISSING_SUBJECT: Final[str] = "Token missing user identifier"
    _ERROR_MISSING_CLAIMS: Final[str] = "Token missing required claims"

    def __init__(self, config: AuthConfig) -> None:
        self._config = config

    def hash_password(self, password: str) -> str:
        prehashed = self._prehash_password(password)
        return bcrypt.hashpw(prehashed, bcrypt.gensalt()).decode(
            self._config.password_encoding
        )

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        prehashed = self._prehash_password(plain_password)
        try:
            return bcrypt.checkpw(
                prehashed, password_hash.encode(self._config.password_encoding)
            )
        except (ValueError, AttributeError):
            return False

    def create_token(self, user_id: str, role: str) -> TokenResponse:
        if not user_id:
            raise ValueError("user_id cannot be empty")
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self._config.access_token_expire_minutes)
        payload = {
            self._CLAIM_SUBJECT: user_id,
            self._CLAIM_ROLE: role,
            self._CLAIM_ISSUED_AT: int(now.timestamp()),
            self._CLAIM_EXPIRATION: int(expires_at.timestamp()),
        }
        token = jwt.encode(
            payload, self._config.secret_key, algorithm=self._config.algorithm
        )
        return TokenResponse(access_token=token)

    def decode_token(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token, self._config.secret_key, algorithms=[self._config.algorithm]
            )
        except InvalidTokenError as exc:
            raise AuthenticationError(self._ERROR_INVALID_TOKEN) from exc

        subject = payload.get(self._CLAIM_SUBJECT)
        if not isinstance(subject, str) or not subject:
            raise AuthenticationError(self._ERROR_MISSING_SUBJECT)

        role = payload.get(self._CLAIM_ROLE)
        if not isinstance(role, str):
            raise AuthenticationError(self._ERROR_MISSING_CLAIMS)

        return TokenClaims(user_id=subject, role=role)

    def _prehash_password(self, password: str) -> bytes:
        return hashlib.sha256(
            password.encode(self._config.password_encoding)
        ).digest()
