"""Faculty persistence repository."""

from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from api.db.tables import faculties
from api.faculties.schemas import FacultyOut
from common.core.exceptions import ConflictError
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


class FacultyRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        with self._engine.begin() as conn:
            faculties.create(conn, checkfirst=True)

    def create(self, university_id: str, name: str, code: str) -> FacultyOut:
        uid = str(uuid4())
        stmt = (
            faculties.insert()
            .values(id=uid, university_id=university_id, name=name, code=code.upper())
            .returning(
                faculties.c.id,
                faculties.c.university_id,
                faculties.c.name,
                faculties.c.code,
                faculties.c.is_active,
                faculties.c.created_at,
            )
        )
        try:
            with self._engine.begin() as conn:
                row = conn.execute(stmt).mappings().first()
        except IntegrityError as exc:
            raise ConflictError(f"Faculty code '{code}' already exists in this university") from exc
        assert row is not None
        return self._map(row)

    def list_by_university(self, university_id: str) -> list[FacultyOut]:
        stmt = (
            select(
                faculties.c.id,
                faculties.c.university_id,
                faculties.c.name,
                faculties.c.code,
                faculties.c.is_active,
                faculties.c.created_at,
            )
            .where(
                faculties.c.university_id == university_id,
                faculties.c.is_active.is_(True),
            )
            .order_by(faculties.c.name)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [self._map(r) for r in rows]

    def get(self, faculty_id: str) -> FacultyOut | None:
        stmt = select(
            faculties.c.id,
            faculties.c.university_id,
            faculties.c.name,
            faculties.c.code,
            faculties.c.is_active,
            faculties.c.created_at,
        ).where(faculties.c.id == faculty_id)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return self._map(row) if row else None

    def _map(self, row: Mapping[str, Any]) -> FacultyOut:
        return FacultyOut(
            id=str(row["id"]),
            university_id=str(row["university_id"]),
            name=str(row["name"]),
            code=str(row["code"]),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or datetime.utcnow(),
        )
