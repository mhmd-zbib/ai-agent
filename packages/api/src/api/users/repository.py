"""User persistence repository.

Manages two tables atomically:
  • users            — public profile (display_name, role, onboarding_complete)
  • auth_credentials — secrets only  (email, password_hash)

Both rows share the same UUID primary key and are always created / deleted together.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from datetime import datetime as dt
from typing import Any, Mapping
from uuid import uuid4

from api.db.tables import auth_credentials, users
from api.users.config import RepositoryConfig
from api.users.schemas import UserOut
from common.core.enums import Role
from common.core.exceptions import ConflictError
from sqlalchemy import select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


@dataclass(frozen=True)
class UserCredential:
    """Internal record used during login — includes password_hash."""

    user_id: str
    password_hash: str
    role: str
    onboarding_complete: bool


@dataclass(frozen=True)
class UserRecord:
    """Internal full record (profile + email)."""

    id: str
    email: str
    display_name: str | None
    role: str
    onboarding_complete: bool
    created_at: dt


class UserRepository:
    """Repository for user persistence — owns both users and auth_credentials tables."""

    def __init__(self, engine: Engine, config: RepositoryConfig | None = None) -> None:
        self._engine = engine
        self._config = config or RepositoryConfig()

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def ensure_schema(self) -> None:
        with self._engine.begin() as conn:
            users.create(conn, checkfirst=True)
            auth_credentials.create(conn, checkfirst=True)
            # Idempotent column migrations for existing deployments
            conn.execute(
                text("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(100)")
            )
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS"
                    " onboarding_complete BOOLEAN NOT NULL DEFAULT FALSE"
                )
            )
            # Migrate legacy password_hash column into auth_credentials (old schema)
            try:
                conn.execute(
                    text(
                        "INSERT INTO auth_credentials (user_id, password_hash, created_at)"
                        " SELECT id, password_hash, created_at FROM users"
                        " WHERE password_hash IS NOT NULL"
                        "   AND id NOT IN (SELECT user_id FROM auth_credentials)"
                    )
                )
            except Exception:
                pass  # column may not exist on old schema — safe to skip

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def create(
        self,
        email: str,
        password_hash: str,
        display_name: str | None = None,
        role: str = "USER",
    ) -> UserOut:
        user_id = str(uuid4())
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    users.insert().values(
                        id=user_id,
                        email=email,
                        display_name=display_name,
                        role=role,
                    )
                )
                conn.execute(
                    auth_credentials.insert().values(
                        user_id=user_id,
                        password_hash=password_hash,
                    )
                )
        except IntegrityError as exc:
            raise ConflictError("User with this email already exists") from exc
        return UserOut(
            id=user_id,
            email=email,
            display_name=display_name,
            role=Role(role),
            onboarding_complete=False,
        )

    def update_role(self, user_id: str, role: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(update(users).where(users.c.id == user_id).values(role=role))

    def mark_onboarding_complete(self, user_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                update(users)
                .where(users.c.id == user_id)
                .values(onboarding_complete=True)
            )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_credential_by_email(self, email: str) -> UserCredential | None:
        stmt = (
            select(
                auth_credentials.c.password_hash,
                users.c.id.label("user_id"),
                users.c.role,
                users.c.onboarding_complete,
            )
            .join(users, users.c.id == auth_credentials.c.user_id)
            .where(users.c.email == email)
            .limit(1)
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return self._map_credential(row) if row is not None else None

    def get_by_id(self, user_id: str) -> UserOut | None:
        stmt = (
            select(
                users.c.id,
                users.c.email,
                users.c.display_name,
                users.c.role,
                users.c.onboarding_complete,
                users.c.created_at,
            )
            .where(users.c.id == user_id)
            .limit(1)
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return self._map_out(row) if row is not None else None

    def has_any_admin(self) -> bool:
        stmt = select(users.c.id).where(users.c.role == Role.ADMIN.value).limit(1)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).first()
        return row is not None

    def get_all(self, limit: int = 20, offset: int = 0) -> list[UserOut]:
        stmt = (
            select(
                users.c.id,
                users.c.email,
                users.c.display_name,
                users.c.role,
                users.c.onboarding_complete,
                users.c.created_at,
            )
            .order_by(users.c.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [self._map_out(row) for row in rows]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _map_credential(self, row: Mapping[str, Any]) -> UserCredential:
        return UserCredential(
            user_id=str(row["user_id"]),
            password_hash=str(row["password_hash"]),
            role=str(row["role"]),
            onboarding_complete=bool(row["onboarding_complete"]),
        )

    def _map_out(self, row: Mapping[str, Any]) -> UserOut:
        return UserOut(
            id=str(row["id"]),
            email=str(row["email"]),
            display_name=str(row["display_name"]) if row["display_name"] else None,
            role=Role(str(row["role"])),
            onboarding_complete=bool(row["onboarding_complete"]),
        )
