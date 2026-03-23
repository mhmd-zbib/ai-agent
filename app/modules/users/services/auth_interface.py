from abc import ABC, abstractmethod

from app.modules.users.schemas.response import TokenResponse


class TokenClaims:
    """Decoded JWT claims containing user identity and profile fields."""

    __slots__ = ("user_id", "university", "major")

    def __init__(self, user_id: str, university: str, major: str) -> None:
        self.user_id = user_id
        self.university = university
        self.major = major


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
    def create_token(self, user_id: str, university: str, major: str) -> TokenResponse:
        """Create an access token for a user."""
        pass

    @abstractmethod
    def decode_token(self, token: str) -> TokenClaims:
        """Decode and validate a token, returning claims."""
        pass
