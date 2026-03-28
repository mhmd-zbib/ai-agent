"""Course persistence repository."""

from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from api.db.tables import courses
from api.courses.schemas import CourseOut
from common.core.exceptions import ConflictError
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError


class CourseRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        with self._engine.begin() as conn:
            courses.create(conn, checkfirst=True)

    def create(self, university_id: str, code: str, name: str, credits: int | None) -> CourseOut:
        uid = str(uuid4())
        stmt = (
            courses.insert()
            .values(
                id=uid,
                university_id=university_id,
                code=code.upper(),
                name=name,
                credits=credits,
            )
            .returning(
                courses.c.id,
                courses.c.university_id,
                courses.c.code,
                courses.c.name,
                courses.c.credits,
                courses.c.is_active,
                courses.c.created_at,
            )
        )
        try:
            with self._engine.begin() as conn:
                row = conn.execute(stmt).mappings().first()
        except IntegrityError as exc:
            raise ConflictError(f"Course code '{code}' already exists in this university") from exc
        assert row is not None
        return self._map(row)

    def list_by_university(self, university_id: str) -> list[CourseOut]:
        stmt = (
            select(
                courses.c.id,
                courses.c.university_id,
                courses.c.code,
                courses.c.name,
                courses.c.credits,
                courses.c.is_active,
                courses.c.created_at,
            )
            .where(
                courses.c.university_id == university_id,
                courses.c.is_active.is_(True),
            )
            .order_by(courses.c.code)
        )
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [self._map(r) for r in rows]

    def get(self, course_id: str) -> CourseOut | None:
        stmt = select(
            courses.c.id,
            courses.c.university_id,
            courses.c.code,
            courses.c.name,
            courses.c.credits,
            courses.c.is_active,
            courses.c.created_at,
        ).where(courses.c.id == course_id)
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return self._map(row) if row else None

    def get_many(self, course_ids: list[str]) -> list[CourseOut]:
        if not course_ids:
            return []
        stmt = select(
            courses.c.id,
            courses.c.university_id,
            courses.c.code,
            courses.c.name,
            courses.c.credits,
            courses.c.is_active,
            courses.c.created_at,
        ).where(courses.c.id.in_(course_ids))
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [self._map(r) for r in rows]

    def _map(self, row: Mapping[str, Any]) -> CourseOut:
        return CourseOut(
            id=str(row["id"]),
            university_id=str(row["university_id"]),
            code=str(row["code"]),
            name=str(row["name"]),
            credits=int(row["credits"]) if row["credits"] is not None else None,
            is_active=bool(row["is_active"]),
            created_at=row["created_at"] or datetime.utcnow(),
        )
