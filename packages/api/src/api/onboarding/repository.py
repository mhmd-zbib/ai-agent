"""Onboarding persistence repositories.

student_profiles     — academic context (FK ids to reference tables + degree/year/courses)
learning_preferences — AI personalization
"""

from datetime import UTC, datetime
from typing import Any, Mapping

from api.db.tables import (
    faculties,
    learning_preferences,
    majors,
    student_profiles,
    universities,
)
from api.onboarding.schemas import (
    AcademicProfileIn,
    AcademicProfileOut,
    LearningPreferencesIn,
    LearningPreferencesOut,
)
from common.core.enums import (
    DegreeLevel,
    DifficultyLevel,
    ExplanationStyle,
    LearningGoal,
    PreferredFormat,
    PreferredLanguage,
    StudyFrequency,
)
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine


class StudentProfileRepository:
    """Manages the student_profiles table."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        with self._engine.begin() as conn:
            student_profiles.create(conn, checkfirst=True)

    def upsert(self, user_id: str, payload: AcademicProfileIn) -> AcademicProfileOut:
        stmt = pg_insert(student_profiles).values(
            user_id=user_id,
            university_id=payload.university_id,
            faculty_id=payload.faculty_id,
            major_id=payload.major_id,
            degree_level=payload.degree_level.value,
            academic_year=payload.academic_year,
            course_ids=payload.course_ids,
            updated_at=func.now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "university_id": stmt.excluded.university_id,
                "faculty_id": stmt.excluded.faculty_id,
                "major_id": stmt.excluded.major_id,
                "degree_level": stmt.excluded.degree_level,
                "academic_year": stmt.excluded.academic_year,
                "course_ids": stmt.excluded.course_ids,
                "updated_at": func.now(),
            },
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)
        result = self.get(user_id)
        assert result is not None
        return result

    def get(self, user_id: str) -> AcademicProfileOut | None:
        stmt = (
            select(
                student_profiles.c.user_id,
                student_profiles.c.university_id,
                universities.c.name.label("university_name"),
                student_profiles.c.faculty_id,
                faculties.c.name.label("faculty_name"),
                student_profiles.c.major_id,
                majors.c.name.label("major_name"),
                student_profiles.c.degree_level,
                student_profiles.c.academic_year,
                student_profiles.c.course_ids,
                student_profiles.c.created_at,
                student_profiles.c.updated_at,
            )
            .join(universities, universities.c.id == student_profiles.c.university_id)
            .outerjoin(faculties, faculties.c.id == student_profiles.c.faculty_id)
            .join(majors, majors.c.id == student_profiles.c.major_id)
            .where(student_profiles.c.user_id == user_id)
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return self._map(row) if row is not None else None

    def _map(self, row: Mapping[str, Any]) -> AcademicProfileOut:
        course_ids: list[str] = list(row["course_ids"]) if row["course_ids"] else []
        return AcademicProfileOut(
            user_id=str(row["user_id"]),
            university_id=str(row["university_id"]),
            university_name=str(row["university_name"]),
            faculty_id=str(row["faculty_id"]) if row["faculty_id"] else None,
            faculty_name=str(row["faculty_name"]) if row["faculty_name"] else None,
            major_id=str(row["major_id"]),
            major_name=str(row["major_name"]),
            degree_level=DegreeLevel(str(row["degree_level"])),
            academic_year=int(row["academic_year"]),
            course_ids=course_ids,
            created_at=row["created_at"] or datetime.now(UTC),
            updated_at=row["updated_at"] or datetime.now(UTC),
        )


class LearningPreferencesRepository:
    """Manages the learning_preferences table."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_schema(self) -> None:
        with self._engine.begin() as conn:
            learning_preferences.create(conn, checkfirst=True)

    def upsert(self, user_id: str, payload: LearningPreferencesIn) -> LearningPreferencesOut:
        stmt = pg_insert(learning_preferences).values(
            user_id=user_id,
            explanation_style=payload.explanation_style.value,
            preferred_language=payload.preferred_language.value,
            difficulty_level=payload.difficulty_level.value,
            goals=[g.value for g in payload.goals],
            weak_areas=payload.weak_areas,
            study_frequency=payload.study_frequency.value,
            preferred_formats=[f.value for f in payload.preferred_formats],
            updated_at=func.now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "explanation_style": stmt.excluded.explanation_style,
                "preferred_language": stmt.excluded.preferred_language,
                "difficulty_level": stmt.excluded.difficulty_level,
                "goals": stmt.excluded.goals,
                "weak_areas": stmt.excluded.weak_areas,
                "study_frequency": stmt.excluded.study_frequency,
                "preferred_formats": stmt.excluded.preferred_formats,
                "updated_at": func.now(),
            },
        ).returning(learning_preferences)
        with self._engine.begin() as conn:
            row = conn.execute(stmt).mappings().first()
        assert row is not None
        return self._map(row)

    def get(self, user_id: str) -> LearningPreferencesOut | None:
        stmt = select(learning_preferences).where(
            learning_preferences.c.user_id == user_id
        )
        with self._engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        return self._map(row) if row is not None else None

    def _map(self, row: Mapping[str, Any]) -> LearningPreferencesOut:
        def _load(val: Any) -> list[str]:
            return list(val) if val else []

        return LearningPreferencesOut(
            user_id=str(row["user_id"]),
            explanation_style=ExplanationStyle(str(row["explanation_style"])),
            preferred_language=PreferredLanguage(str(row["preferred_language"])),
            difficulty_level=DifficultyLevel(str(row["difficulty_level"])),
            goals=[LearningGoal(g) for g in _load(row["goals"])],
            weak_areas=str(row["weak_areas"]) if row["weak_areas"] else None,
            study_frequency=StudyFrequency(str(row["study_frequency"])),
            preferred_formats=[PreferredFormat(f) for f in _load(row["preferred_formats"])],
            created_at=row["created_at"] or datetime.now(UTC),
            updated_at=row["updated_at"] or datetime.now(UTC),
        )
