from datetime import UTC, datetime, timedelta
import hashlib
from typing import Final

import bcrypt
import jwt
from jwt import InvalidTokenError

from app.modules.users.config import AuthConfig
from app.modules.users.schemas.response import TokenResponse
from app.modules.users.services.auth_interface import IAuthService, TokenClaims
from app.shared.exceptions import AuthenticationError


class AuthService(IAuthService):
    """
    Authentication service implementing JWT token management and password hashing.
    Uses bcrypt with SHA256 pre-hashing for secure password storage.
    Implements IAuthService interface for dependency inversion.
    """

    # JWT Claim Keys
    _CLAIM_SUBJECT: Final[str] = "sub"
    _CLAIM_ISSUED_AT: Final[str] = "iat"
    _CLAIM_EXPIRATION: Final[str] = "exp"
    _CLAIM_UNIVERSITY: Final[str] = "university"
    _CLAIM_MAJOR: Final[str] = "major"

    # Error Messages
    _ERROR_INVALID_TOKEN: Final[str] = "Invalid or expired token"
    _ERROR_MISSING_SUBJECT: Final[str] = "Token missing user identifier"
    _ERROR_MISSING_CLAIMS: Final[str] = "Token missing required claims"
    _ERROR_INVALID_PASSWORD_HASH: Final[str] = "Invalid password hash format"

    def __init__(self, config: AuthConfig) -> None:
        """
        Initialize the authentication service.

        Args:
            config: Authentication configuration with JWT and password settings

        Raises:
            ValueError: If configuration is invalid
        """
        self._config = config

    def hash_password(self, password: str) -> str:
        """
        Hash a password using bcrypt with SHA256 pre-hashing.

        Pre-hashing with SHA256 ensures bcrypt receives fixed-size input (<72 bytes)
        regardless of original password length.

        Args:
            password: Plain-text password to hash

        Returns:
            UTF-8 encoded bcrypt hash string
        """
        prehashed = self._prehash_password(password)
        return bcrypt.hashpw(prehashed, bcrypt.gensalt()).decode(
            self._config.password_encoding
        )

    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        """
        Verify a password against its hash.

        Args:
            plain_password: Plain-text password to verify
            password_hash: Bcrypt hash to check against

        Returns:
            True if password matches hash, False otherwise
        """
        prehashed = self._prehash_password(plain_password)
        try:
            return bcrypt.checkpw(
                prehashed, password_hash.encode(self._config.password_encoding)
            )
        except (ValueError, AttributeError):
            # Log the error but don't expose details to caller
            # ValueError: invalid hash format
            # AttributeError: password_hash is None or invalid type
            return False

    def create_token(self, user_id: str, university: str, major: str) -> TokenResponse:
        """
        Create a JWT access token for a user.

        Args:
            user_id: Unique identifier for the user
            university: Student's university enum value
            major: Student's major enum value

        Returns:
            TokenResponse containing the JWT token
        """
        if not user_id:
            raise ValueError("user_id cannot be empty")

        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=self._config.access_token_expire_minutes)

        payload = {
            self._CLAIM_SUBJECT: user_id,
            self._CLAIM_UNIVERSITY: university,
            self._CLAIM_MAJOR: major,
            self._CLAIM_ISSUED_AT: int(now.timestamp()),
            self._CLAIM_EXPIRATION: int(expires_at.timestamp()),
        }

        token = jwt.encode(
            payload, self._config.secret_key, algorithm=self._config.algorithm
        )
        return TokenResponse(access_token=token)

    def decode_token(self, token: str) -> TokenClaims:
        """
        Decode and validate a JWT token, extracting user claims.

        Args:
            token: JWT token to decode

        Returns:
            TokenClaims with user_id, university, and major

        Raises:
            AuthenticationError: If token is invalid, expired, or malformed
        """
        try:
            payload = jwt.decode(
                token,
                self._config.secret_key,
                algorithms=[self._config.algorithm],
            )
        except InvalidTokenError as exc:
            raise AuthenticationError(self._ERROR_INVALID_TOKEN) from exc

        subject = payload.get(self._CLAIM_SUBJECT)
        if not isinstance(subject, str) or not subject:
            raise AuthenticationError(self._ERROR_MISSING_SUBJECT)

        university = payload.get(self._CLAIM_UNIVERSITY)
        major = payload.get(self._CLAIM_MAJOR)
        if not isinstance(university, str) or not isinstance(major, str):
            raise AuthenticationError(self._ERROR_MISSING_CLAIMS)

        return TokenClaims(user_id=subject, university=university, major=major)

    def _prehash_password(self, password: str) -> bytes:
        """
        Pre-hash password with SHA256 before bcrypt.

        This ensures bcrypt always receives fixed-size input regardless of
        password length, avoiding bcrypt's 72-byte limitation.

        Args:
            password: Plain-text password

        Returns:
            SHA256 digest as bytes
        """
        return hashlib.sha256(password.encode(self._config.password_encoding)).digest()
