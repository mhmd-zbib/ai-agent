from app.modules.users.repositories.user_repository import UserRepository
from app.modules.users.schemas.request import UserCreate
from app.modules.users.schemas.response import UserOut


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    def create_user(self, payload: UserCreate) -> UserOut:
        return self._repository.create(payload.email, payload.password)

