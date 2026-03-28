"""University service."""

from api.universities.repository import UniversityRepository
from api.universities.schemas import UniversityIn, UniversityOut
from common.core.exceptions import NotFoundError


class UniversityService:
    def __init__(self, repository: UniversityRepository) -> None:
        self._repo = repository

    def create(self, payload: UniversityIn) -> UniversityOut:
        return self._repo.create(payload.name, payload.code)

    def list_active(self) -> list[UniversityOut]:
        return self._repo.list_active()

    def get(self, university_id: str) -> UniversityOut:
        uni = self._repo.get(university_id)
        if uni is None:
            raise NotFoundError(f"University '{university_id}' not found")
        return uni

    def deactivate(self, university_id: str) -> None:
        self.get(university_id)  # raises 404 if missing
        self._repo.deactivate(university_id)
