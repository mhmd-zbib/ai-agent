"""Major persistence repository."""

from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from api.db.tables import majors
from api.majors.schemas import MajorOut
from common.core.exceptions import ConflictError
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


class MajorRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        with self._engine.begin() as conn:
            majors.create(conn, checkfirst=True)

    def create(self, faculty_id: str, name: str, code: str) -> MajorOut:
        uid = str(uuid4())
        stmt = (
            majors.insert()
            .values(id=uid, faculty_id=faculty_id, name=name, code=code.upper())
            .returning(
                majors.c.id,
                majors.c.faculty_id,
                majors.c.name,
                majors.c.code,
                majors.c.is_active,
                majors.c.created_at,
            )
        )
        try:
            with self._engine.begin() as conn:
                row = conn.execute(stmt).mappings().first()
        except IntegrityError as exc:
            raise ConflictError(f"Major code '{code}' already exists in this faculty") from exc
        assert row is not None
        return self._map(row)

    def list_by_faculty(self, faculty_id: str) -> list[MajorOut]:
        stmt = (
            select(
                majors.c.id,
                majors.c.faculty_id,
                majors.c.name,
                majors.c.code,
                majors.c.is_active,
                majors.c.created_at,
            )
            .where(
                majors.c.faculty_id == faculty_id,
                majors.c.is_active.is_(True),
            )
            .order_by(majors.c.name)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [self._map(r) for r in rows]

    def get(self, major_id: str) -> MajorOut | None:
        stmt = select(
            majors.c.id,
            majors.c.faculty_id,
            majors.c.name,
            majors.c.code,
            majors.c.is_active,
            majors.c.created_at,
        ).where(majors.c.id == major_id)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return self._map(row) if row else None

    def _map(self, row: Mapping[str, Any]) -> MajorOut:
        return MajorOut(
            id=str(row["id"]),
            faculty_id=str(row["faculty_id"]),
            name=str(row["name"]),
            code=str(row["code"]),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or datetime.utcnow(),
        )
