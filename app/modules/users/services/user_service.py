from typing import Final

from app.modules.users.repositories.user_repository import UserRepository
from app.modules.users.schemas.request import LoginRequest, UserCreate
from app.modules.users.schemas.response import TokenResponse, UserOut
from app.modules.users.services.auth_interface import IAuthService
from app.shared.exceptions import AuthenticationError, ConflictError


class UserService:
    """
    User service coordinating authentication and user management.

    Implements Single Responsibility Principle:
    - Delegates authentication logic to IAuthService
    - Delegates persistence to UserRepository
    - Orchestrates workflows between services

    Implements Dependency Inversion Principle:
    - Depends on IAuthService abstraction, not concrete AuthService
    """

    # Error Messages
    _ERROR_INVALID_CREDENTIALS: Final[str] = "Invalid email or password"
    _ERROR_INVALID_TOKEN: Final[str] = "Invalid or expired token"
    _ERROR_USER_NOT_FOUND: Final[str] = "User not found"

    def __init__(self, repository: UserRepository, auth_service: IAuthService) -> None:
        """
        Initialize the user service.

        Args:
            repository: Repository for user persistence
            auth_service: Authentication service (interface for DIP)
        """
        self._repository = repository
        self._auth_service = auth_service

    def register_user(self, payload: UserCreate) -> UserOut:
        """
        Register a new user.

        Args:
            payload: User registration data (email, password, university, major)

        Returns:
            UserOut with the created user's information

        Raises:
            ConflictError: If a user with this email already exists
        """
        password_hash = self._auth_service.hash_password(payload.password)

        try:
            return self._repository.create(
                payload.email,
                password_hash,
                payload.university.value,
                payload.major.value,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc

    def login(self, payload: LoginRequest) -> TokenResponse:
        """
        Authenticate a user and generate an access token.

        Args:
            payload: Login credentials (email and password)

        Returns:
            TokenResponse containing the JWT access token

        Raises:
            AuthenticationError: If credentials are invalid
        """
        # Retrieve user by email
        user = self._repository.get_by_email(payload.email)
        if user is None:
            raise AuthenticationError(self._ERROR_INVALID_CREDENTIALS)

        # Verify password
        if not self._auth_service.verify_password(payload.password, user.password_hash):
            raise AuthenticationError(self._ERROR_INVALID_CREDENTIALS)

        # Generate and return token
        return self._auth_service.create_token(user.id, user.university, user.major)

    def get_user_from_token(self, token: str) -> UserOut:
        """
        Retrieve user information from a JWT token.

        Args:
            token: JWT access token

        Returns:
            UserOut with the authenticated user's information

        Raises:
            AuthenticationError: If token is invalid or user not found
        """
        claims = self._auth_service.decode_token(token)

        user = self._repository.get_by_id(claims.user_id)
        if user is None:
            raise AuthenticationError(self._ERROR_INVALID_TOKEN)

        return user

    def close(self) -> None:
        """Close service resources."""
        self._repository.close()
