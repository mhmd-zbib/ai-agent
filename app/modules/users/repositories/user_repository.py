from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Mapping
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.modules.users.config import RepositoryConfig
from app.modules.users.schemas.response import UserOut
from app.shared.enums import Major, University


@dataclass(frozen=True)
class UserRecord:
    """
    Internal representation of a user record from database.
    Contains all fields including password_hash for authentication.
    """

    id: str
    email: str
    password_hash: str
    university: str
    major: str
    created_at: datetime


class UserRepository:
    """
    Repository for user persistence operations.
    Implements Repository Pattern with improved type safety and error handling.
    """

    # SQL Queries - defined as constants for reusability and clarity
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

    # Idempotent migrations for columns added after initial table creation
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
        FROM users
        WHERE email = :email
        LIMIT 1
    """

    _SQL_SELECT_BY_ID: Final[str] = """
        SELECT id, email, university, major, created_at
        FROM users
        WHERE id = :id
        LIMIT 1
    """

    # Error Messages
    _ERROR_DUPLICATE_EMAIL: Final[str] = "User with this email already exists"
    _ERROR_USER_NOT_FOUND: Final[str] = "User not found"

    def __init__(self, engine: Engine, config: RepositoryConfig | None = None) -> None:
        """
        Initialize the user repository.

        Args:
            engine: SQLAlchemy engine for database connections
            config: Optional repository configuration (uses defaults if not provided)
        """
        self._engine = engine
        self._config = config or RepositoryConfig()

    def ensure_schema(self) -> None:
        """
        Ensure the users table exists in the database.
        Should be called during application startup.
        """
        with self._engine.begin() as connection:
            connection.execute(text(self._SQL_CREATE_TABLE))
            connection.execute(text(self._SQL_MIGRATE_UNIVERSITY))
            connection.execute(text(self._SQL_MIGRATE_MAJOR))

    def create(
        self, email: str, password_hash: str, university: str, major: str
    ) -> UserOut:
        """
        Create a new user in the database.

        Args:
            email: User's email address (must be unique)
            password_hash: Pre-hashed password
            university: Student's university enum value
            major: Student's major enum value

        Returns:
            UserOut with the created user's information

        Raises:
            ValueError: If a user with this email already exists
        """
        user_id = str(uuid4())

        try:
            with self._engine.begin() as connection:
                connection.execute(
                    text(self._SQL_INSERT_USER),
                    {
                        "id": user_id,
                        "email": email,
                        "password_hash": password_hash,
                        "university": university,
                        "major": major,
                    },
                )
        except IntegrityError as exc:
            raise ValueError(self._ERROR_DUPLICATE_EMAIL) from exc

        return UserOut(
            id=user_id,
            email=email,
            university=University(university),
            major=Major(major),
        )

    def get_by_email(self, email: str) -> UserRecord | None:
        """
        Retrieve a user by email address.

        Args:
            email: Email address to search for

        Returns:
            UserRecord if found, None otherwise
        """
        with self._engine.connect() as connection:
            result = connection.execute(
                text(self._SQL_SELECT_BY_EMAIL),
                {"email": email},
            )
            row = result.mappings().first()

        if row is None:
            return None

        return self._map_to_user_record(row)

    def get_by_id(self, user_id: str) -> UserOut | None:
        """
        Retrieve a user by ID.

        Args:
            user_id: User's unique identifier

        Returns:
            UserOut if found, None otherwise
        """
        with self._engine.connect() as connection:
            result = connection.execute(
                text(self._SQL_SELECT_BY_ID),
                {"id": user_id},
            )
            row = result.mappings().first()

        if row is None:
            return None

        return self._map_to_user_out(row)

    def close(self) -> None:
        """
        Close repository resources.
        Note: Engine lifecycle is managed by application startup/shutdown.
        """
        # Engine lifecycle is owned by app startup/shutdown.
        pass

    def _map_to_user_record(self, row: Mapping[str, Any]) -> UserRecord:
        """
        Map a database row to UserRecord with proper type handling.

        Args:
            row: Database row from SQLAlchemy query

        Returns:
            UserRecord with properly typed fields
        """
        # Defensive handling: use current time if created_at is somehow NULL
        created_at = row["created_at"]
        if created_at is None:
            created_at = datetime.now(UTC)

        return UserRecord(
            id=str(row["id"]),
            email=str(row["email"]),
            password_hash=str(row["password_hash"]),
            university=str(row["university"]),
            major=str(row["major"]),
            created_at=created_at,
        )

    def _map_to_user_out(self, row: Mapping[str, Any]) -> UserOut:
        """
        Map a database row to UserOut with proper type handling.

        Args:
            row: Database row mapping from SQLAlchemy query

        Returns:
            UserOut with properly typed fields
        """
        return UserOut(
            id=str(row["id"]),
            email=str(row["email"]),
            university=University(str(row["university"])),
            major=Major(str(row["major"])),
        )
