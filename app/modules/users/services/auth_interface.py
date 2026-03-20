from abc import ABC, abstractmethod

from app.modules.users.schemas.response import TokenResponse


class IAuthService(ABC):
    """
    Interface for authentication services.
    Implements Dependency Inversion Principle - high-level modules depend on this abstraction.
    """

    @abstractmethod
    def hash_password(self, password: str) -> str:
        """Hash a plain-text password."""
        pass

    @abstractmethod
    def verify_password(self, plain_password: str, password_hash: str) -> bool:
        """Verify a plain-text password against a hash."""
        pass

    @abstractmethod
    def create_token(self, user_id: str) -> TokenResponse:
        """Create an access token for a user."""
        pass

    @abstractmethod
    def decode_subject(self, token: str) -> str:
        """Decode and validate a token, returning the user ID (subject)."""
        pass
