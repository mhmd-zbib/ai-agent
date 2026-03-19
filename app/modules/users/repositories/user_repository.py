from app.modules.users.schemas.response import UserOut


class UserRepository:
    def create(self, email: str, password_hash: str) -> UserOut:  # noqa: ARG002
        return UserOut(id="stub-user", email=email)

    def get_by_email(self, email: str) -> UserOut | None:
        return None

