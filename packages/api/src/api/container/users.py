"""User and admin service factories."""

from sqlalchemy.engine import Engine

from api.admin.service import AdminService
from api.auth.config import AuthConfig
from api.auth.service import AuthService
from api.users.repository import UserRepository
from api.users.service import UserService
from common.core.config import Settings


def create_user_service(settings: Settings, postgres_engine: Engine) -> UserService:
    auth_config = AuthConfig(
        settings.jwt_secret_key or "",
        settings.jwt_algorithm,
        settings.jwt_access_token_expire_minutes,
    )
    repository = UserRepository(postgres_engine)
    repository.ensure_schema()
    return UserService(repository=repository, auth_service=AuthService(auth_config))


def create_admin_service(user_service: UserService, postgres_engine: Engine) -> AdminService:
    return AdminService(
        user_service=user_service,
        user_repository=UserRepository(postgres_engine),
    )
