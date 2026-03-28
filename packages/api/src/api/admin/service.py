"""Admin service — admin-scoped user operations."""

from api.users.repository import UserRepository
from api.users.schemas import AdminUpdateRole, UserCreate, UserOut
from api.users.service import UserService
from common.core.enums import Role
from common.core.log_config import get_logger

logger = get_logger(__name__)


class AdminService:
    """Handles admin-scoped user management: creation, listing, and role updates."""

    def __init__(self, user_service: UserService, user_repository: UserRepository) -> None:
        self._user_service = user_service
        self._repo = user_repository

    def create_admin(
        self,
        email: str,
        password: str,
        display_name: str | None = None,
    ) -> UserOut:
        """Register a new user and immediately promote them to ADMIN."""
        user = self._user_service.register_user(
            UserCreate(email=email, password=password, display_name=display_name)
        )
        self._repo.update_role(user.id, Role.ADMIN.value)
        refreshed = self._repo.get_by_id(user.id)
        assert refreshed is not None
        return refreshed

    def seed_default_admin(self, email: str, password: str) -> None:
        """Create the initial ADMIN account if none exists yet. Idempotent."""
        if self._repo.has_any_admin():
            return
        try:
            self.create_admin(email=email, password=password, display_name="System Admin")
            logger.info("Default admin account created", extra={"email": email})
        except Exception as exc:
            logger.warning(
                "Default admin could not be created",
                extra={"reason": str(exc)},
            )

    def list_users(self, limit: int = 20, offset: int = 0) -> list[UserOut]:
        return self._user_service.list_users(limit=limit, offset=offset)

    def update_user_role(self, user_id: str, payload: AdminUpdateRole) -> UserOut:
        return self._user_service.update_user_role(user_id, payload)
