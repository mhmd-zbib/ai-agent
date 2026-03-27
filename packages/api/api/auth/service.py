"""Authentication and user management services."""

import hashlib
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import uuid4

import bcrypt
import jwt
from api.auth.config import AuthConfig, RepositoryConfig
from api.auth.schemas import LoginRequest, TokenResponse, UserCreate, UserOut
from jwt import InvalidTokenError
from shared.enums import Major, University
from shared.exceptions import AuthenticationError, ConflictError
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


# ---------------------------------------------------------------------------
# Token claims
# ---------------------------------------------------------------------------


class TokenClaims:
    """Decoded JWT claims containing user identity and profile fields."""

    __slots__ = ("user_id", "university", "major")

    def __init__(self, user_id: str, university: str, major: str) -> None:
        self.user_id = user_id
        self.university = university
        self.major = major


# ---------------------------------------------------------------------------
# Auth service interface + implementation
# ---------------------------------------------------------------------------


class IAuthService(ABC):
    """Interface for authentication services (DIP)."""

    @abstractmethod
    def hash_password(self, password: str) -> str: ...

    @abstractmethod
    def verify_password(self, plain_password: str, password_hash: str) -> bool: ...

    @abstractmethod
    def create_token(self, user_id: str, university: str, major: str) -> TokenResponse: ...

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
    _CLAIM_UNIVERSITY: Final[str] = "university"
    _CLAIM_MAJOR: Final[str] = "major"

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

    def create_token(self, user_id: str, university: str, major: str) -> TokenResponse:
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
        token = jwt.encode(payload, self._config.secret_key, algorithm=self._config.algorithm)
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

        university = payload.get(self._CLAIM_UNIVERSITY)
        major = payload.get(self._CLAIM_MAJOR)
        if not isinstance(university, str) or not isinstance(major, str):
            raise AuthenticationError(self._ERROR_MISSING_CLAIMS)

        return TokenClaims(user_id=subject, university=university, major=major)

    def _prehash_password(self, password: str) -> bytes:
        return hashlib.sha256(password.encode(self._config.password_encoding)).digest()


# ---------------------------------------------------------------------------
# User repository
# ---------------------------------------------------------------------------

from dataclasses import dataclass
from datetime import datetime as dt
from typing import Any, Mapping


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str
    password_hash: str
    university: str
    major: str
    created_at: dt


class UserRepository:
    """Repository for user persistence operations."""

    _SQL_CREATE_TABLE: Final[str] = """
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(36) PRIMARY KEY,
            email VARCHAR(320) NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            university VARCHAR(50) NOT NULL,
            major VARCHAR(100) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """
    _SQL_MIGRATE_UNIVERSITY: Final[str] = """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS university VARCHAR(50) NOT NULL DEFAULT 'LIU'
    """
    _SQL_MIGRATE_MAJOR: Final[str] = """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS major VARCHAR(100) NOT NULL DEFAULT 'COMPUTER_SCIENCE'
    """
    _SQL_INSERT_USER: Final[str] = """
        INSERT INTO users (id, email, password_hash, university, major)
        VALUES (:id, :email, :password_hash, :university, :major)
    """
    _SQL_SELECT_BY_EMAIL: Final[str] = """
        SELECT id, email, password_hash, university, major, created_at
        FROM users WHERE email = :email LIMIT 1
    """
    _SQL_SELECT_BY_ID: Final[str] = """
        SELECT id, email, university, major, created_at
        FROM users WHERE id = :id LIMIT 1
    """
    _ERROR_DUPLICATE_EMAIL: Final[str] = "User with this email already exists"

    def __init__(self, engine: Engine, config: RepositoryConfig | None = None) -> None:
        self._engine = engine
        self._config = config or RepositoryConfig()

    def ensure_schema(self) -> None:
        with self._engine.begin() as connection:
            connection.execute(text(self._SQL_CREATE_TABLE))
            connection.execute(text(self._SQL_MIGRATE_UNIVERSITY))
            connection.execute(text(self._SQL_MIGRATE_MAJOR))

    def create(self, email: str, password_hash: str, university: str, major: str) -> UserOut:
        user_id = str(uuid4())
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    text(self._SQL_INSERT_USER),
                    {"id": user_id, "email": email, "password_hash": password_hash,
                     "university": university, "major": major},
                )
        except IntegrityError as exc:
            raise ValueError(self._ERROR_DUPLICATE_EMAIL) from exc
        return UserOut(id=user_id, email=email, university=University(university), major=Major(major))

    def get_by_email(self, email: str) -> UserRecord | None:
        with self._engine.connect() as connection:
            result = connection.execute(text(self._SQL_SELECT_BY_EMAIL), {"email": email})
            row = result.mappings().first()
        if row is None:
            return None
        return self._map_to_user_record(row)

    def get_by_id(self, user_id: str) -> UserOut | None:
        with self._engine.connect() as connection:
            result = connection.execute(text(self._SQL_SELECT_BY_ID), {"id": user_id})
            row = result.mappings().first()
        if row is None:
            return None
        return self._map_to_user_out(row)

    def close(self) -> None:
        pass

    def _map_to_user_record(self, row: Mapping[str, Any]) -> UserRecord:
        created_at = row["created_at"]
        if created_at is None:
            created_at = datetime.now(UTC)
        return UserRecord(
            id=str(row["id"]), email=str(row["email"]),
            password_hash=str(row["password_hash"]), university=str(row["university"]),
            major=str(row["major"]), created_at=created_at,
        )

    def _map_to_user_out(self, row: Mapping[str, Any]) -> UserOut:
        return UserOut(
            id=str(row["id"]), email=str(row["email"]),
            university=University(str(row["university"])), major=Major(str(row["major"])),
        )


# ---------------------------------------------------------------------------
# User service
# ---------------------------------------------------------------------------


class UserService:
    """User service coordinating authentication and user management."""

    _ERROR_INVALID_CREDENTIALS: Final[str] = "Invalid email or password"
    _ERROR_INVALID_TOKEN: Final[str] = "Invalid or expired token"

    def __init__(self, repository: UserRepository, auth_service: IAuthService) -> None:
        self._repository = repository
        self._auth_service = auth_service

    def register_user(self, payload: UserCreate) -> UserOut:
        password_hash = self._auth_service.hash_password(payload.password)
        try:
            return self._repository.create(
                payload.email, password_hash, payload.university.value, payload.major.value
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self._repository.get_by_email(payload.email)
        if user is None:
            raise AuthenticationError(self._ERROR_INVALID_CREDENTIALS)
        if not self._auth_service.verify_password(payload.password, user.password_hash):
            raise AuthenticationError(self._ERROR_INVALID_CREDENTIALS)
        return self._auth_service.create_token(user.id, user.university, user.major)

    def get_user_from_token(self, token: str) -> UserOut:
        claims = self._auth_service.decode_token(token)
        user = self._repository.get_by_id(claims.user_id)
        if user is None:
            raise AuthenticationError(self._ERROR_INVALID_TOKEN)
        return user

    def close(self) -> None:
        self._repository.close()
