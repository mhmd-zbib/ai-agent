"""Faculty service."""

from api.faculties.repository import FacultyRepository
from api.faculties.schemas import FacultyIn, FacultyOut
from common.core.exceptions import NotFoundError


class FacultyService:
    def __init__(self, repository: FacultyRepository) -> None:
        self._repo = repository

    def create(self, payload: FacultyIn) -> FacultyOut:
        return self._repo.create(payload.university_id, payload.name, payload.code)

    def list_by_university(self, university_id: str) -> list[FacultyOut]:
        return self._repo.list_by_university(university_id)

    def get(self, faculty_id: str) -> FacultyOut:
        fac = self._repo.get(faculty_id)
        if fac is None:
            raise NotFoundError(f"Faculty '{faculty_id}' not found")
        return fac
