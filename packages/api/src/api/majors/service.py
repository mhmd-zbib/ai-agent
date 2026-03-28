"""Major service."""

from api.majors.repository import MajorRepository
from api.majors.schemas import MajorIn, MajorOut
from common.core.exceptions import NotFoundError


class MajorService:
    def __init__(self, repository: MajorRepository) -> None:
        self._repo = repository

    def create(self, payload: MajorIn) -> MajorOut:
        return self._repo.create(payload.faculty_id, payload.name, payload.code)

    def list_by_faculty(self, faculty_id: str) -> list[MajorOut]:
        return self._repo.list_by_faculty(faculty_id)

    def get(self, major_id: str) -> MajorOut:
        maj = self._repo.get(major_id)
        if maj is None:
            raise NotFoundError(f"Major '{major_id}' not found")
        return maj
