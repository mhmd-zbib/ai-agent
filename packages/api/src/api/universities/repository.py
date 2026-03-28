"""University persistence repository."""

from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from api.db.tables import universities
from api.universities.schemas import UniversityOut
from common.core.exceptions import ConflictError
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


class UniversityRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        with self._engine.begin() as conn:
            universities.create(conn, checkfirst=True)

    def create(self, name: str, code: str) -> UniversityOut:
        uid = str(uuid4())
        stmt = (
            universities.insert()
            .values(id=uid, name=name, code=code.upper())
            .returning(
                universities.c.id,
                universities.c.name,
                universities.c.code,
                universities.c.is_active,
                universities.c.created_at,
            )
        )
        try:
            with self._engine.begin() as conn:
                row = conn.execute(stmt).mappings().first()
        except IntegrityError as exc:
            raise ConflictError("University with name or code already exists") from exc
        assert row is not None
        return self._map(row)

    def list_active(self) -> list[UniversityOut]:
        stmt = (
            select(
                universities.c.id,
                universities.c.name,
                universities.c.code,
                universities.c.is_active,
                universities.c.created_at,
            )
            .where(universities.c.is_active.is_(True))
            .order_by(universities.c.name)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [self._map(r) for r in rows]

    def get(self, university_id: str) -> UniversityOut | None:
        stmt = select(
            universities.c.id,
            universities.c.name,
            universities.c.code,
            universities.c.is_active,
            universities.c.created_at,
        ).where(universities.c.id == university_id)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return self._map(row) if row else None

    def deactivate(self, university_id: str) -> None:
        stmt = (
            update(universities)
            .where(universities.c.id == university_id)
            .values(is_active=False)
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)

    def _map(self, row: Mapping[str, Any]) -> UniversityOut:
        return UniversityOut(
            id=str(row["id"]),
            name=str(row["name"]),
            code=str(row["code"]),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or datetime.utcnow(),
        )
