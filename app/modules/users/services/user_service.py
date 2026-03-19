from app.modules.users.repositories.user_repository import UserRepository
from app.modules.users.schemas.request import LoginRequest, UserCreate
from app.modules.users.schemas.response import TokenResponse, UserOut
from app.modules.users.services.auth_service import AuthService
from app.shared.exceptions import AuthenticationError, ConflictError


class UserService:
    def __init__(self, repository: UserRepository, auth_service: AuthService) -> None:
        self._repository = repository
        self._auth_service = auth_service

    def register_user(self, payload: UserCreate) -> UserOut:
        password_hash = self._auth_service.hash_password(payload.password)
        try:
            return self._repository.create(payload.email, password_hash)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

    def login(self, payload: LoginRequest) -> TokenResponse:
        user = self._repository.get_by_email(payload.email)
        if user is None:
            raise AuthenticationError("Invalid email or password.")

        if not self._auth_service.verify_password(payload.password, user.password_hash):
            raise AuthenticationError("Invalid email or password.")

        return self._auth_service.create_token(user.id)

    def get_user_from_token(self, token: str) -> UserOut:
        subject = self._auth_service.decode_subject(token)
        user = self._repository.get_by_id(subject)
        if user is None:
            raise AuthenticationError("Invalid or expired token.")
        return user

    def close(self) -> None:
        self._repository.close()
