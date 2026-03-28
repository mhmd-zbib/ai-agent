"""Course service."""

from api.courses.repository import CourseRepository
from api.courses.schemas import CourseIn, CourseOut
from common.core.exceptions import NotFoundError


class CourseService:
    def __init__(self, repository: CourseRepository) -> None:
        self._repo = repository

    def create(self, payload: CourseIn) -> CourseOut:
        return self._repo.create(payload.university_id, payload.code, payload.name, payload.credits)

    def list_by_university(self, university_id: str) -> list[CourseOut]:
        return self._repo.list_by_university(university_id)

    def get(self, course_id: str) -> CourseOut:
        crs = self._repo.get(course_id)
        if crs is None:
            raise NotFoundError(f"Course '{course_id}' not found")
        return crs

    def get_many(self, course_ids: list[str]) -> list[CourseOut]:
        return self._repo.get_many(course_ids)
