"""User management service."""

from typing import Final

from api.auth.schemas import LoginRequest, TokenResponse
from api.auth.service import IAuthService
from api.users.repository import UserRepository
from api.users.schemas import AdminUpdateRole, UserCreate, UserOut
from api.users.config import RepositoryConfig
from common.core.enums import Role
from common.core.exceptions import AuthenticationError, AuthorizationError
from sqlalchemy.engine import Engine


class UserService:
    """Coordinates user management and authentication."""

    _ERROR_INVALID_CREDENTIALS: Final[str] = "Invalid email or password"
    _ERROR_INVALID_TOKEN: Final[str] = "Invalid or expired token"
    _ERROR_USER_NOT_FOUND: Final[str] = "User not found"

    def __init__(self, repository: UserRepository, auth_service: IAuthService) -> None:
        self._repository = repository
        self._auth_service = auth_service

    def register_user(self, payload: UserCreate) -> UserOut:
        password_hash = self._auth_service.hash_password(payload.password)
        return self._repository.create(
            email=payload.email,
            password_hash=password_hash,
            display_name=payload.display_name,
            role=Role.USER.value,
        )

    def login(self, payload: LoginRequest) -> TokenResponse:
        credential = self._repository.get_credential_by_email(payload.email)
        if credential is None or not self._auth_service.verify_password(
            payload.password, credential.password_hash
        ):
            raise AuthenticationError(self._ERROR_INVALID_CREDENTIALS)
        return self._auth_service.create_token(credential.user_id, credential.role)

    def get_user_from_token(self, token: str) -> UserOut:
        claims = self._auth_service.decode_token(token)
        user = self._repository.get_by_id(claims.user_id)
        if user is None:
            raise AuthenticationError(self._ERROR_INVALID_TOKEN)
        return user

    def get_user_by_id(self, user_id: str) -> UserOut:
        user = self._repository.get_by_id(user_id)
        if user is None:
            raise AuthorizationError(self._ERROR_USER_NOT_FOUND)
        return user

    def list_users(self, limit: int = 20, offset: int = 0) -> list[UserOut]:
        return self._repository.get_all(limit=limit, offset=offset)

    def update_user_role(self, user_id: str, payload: AdminUpdateRole) -> UserOut:
        self._repository.update_role(user_id, payload.role.value)
        return self.get_user_by_id(user_id)

    def close(self) -> None:
        pass
