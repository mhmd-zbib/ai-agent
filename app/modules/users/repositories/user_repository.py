from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from app.modules.users.schemas.response import UserOut


@dataclass(frozen=True)
class UserRecord:
    id: str
    email: str
    password_hash: str
    created_at: datetime


class UserRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        id VARCHAR(36) PRIMARY KEY,
                        email VARCHAR(320) NOT NULL UNIQUE,
                        password_hash TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
            )

    def create(self, email: str, password_hash: str) -> UserOut:
        user_id = str(uuid4())
        try:
            with self._engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO users (id, email, password_hash)
                        VALUES (:id, :email, :password_hash)
                        """
                    ),
                    {
                        "id": user_id,
                        "email": email,
                        "password_hash": password_hash,
                    },
                )
        except IntegrityError as exc:
            raise ValueError("User with this email already exists.") from exc

        return UserOut(id=user_id, email=email)

    def get_by_email(self, email: str) -> UserRecord | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT id, email, password_hash, created_at
                        FROM users
                        WHERE email = :email
                        LIMIT 1
                        """
                    ),
                    {"email": email},
                )
                .mappings()
                .first()
            )

        if row is None:
            return None

        created_at = row["created_at"] or datetime.now(UTC)
        return UserRecord(
            id=cast(str, row["id"]),
            email=cast(str, row["email"]),
            password_hash=cast(str, row["password_hash"]),
            created_at=created_at,
        )

    def get_by_id(self, user_id: str) -> UserOut | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT id, email
                        FROM users
                        WHERE id = :id
                        LIMIT 1
                        """
                    ),
                    {"id": user_id},
                )
                .mappings()
                .first()
            )

        if row is None:
            return None

        return UserOut(id=cast(str, row["id"]), email=cast(str, row["email"]))

    def close(self) -> None:
        # Engine lifecycle is owned by app startup/shutdown.
        return
