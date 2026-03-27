from dataclasses import dataclass


@dataclass(frozen=True)
class AuthConfig:
    """
    Configuration for authentication service.
    Extracted magic numbers and hardcoded values for better maintainability.
    """

    # JWT Configuration
    secret_key: str
    algorithm: str
    access_token_expire_minutes: int

    # Password Hashing Configuration
    bcrypt_max_password_length: int = 72
    password_encoding: str = "utf-8"

    # Query Configuration
    query_timeout_seconds: int = 30

    def __post_init__(self) -> None:
        if not self.secret_key:
            raise ValueError("secret_key cannot be empty")
        if self.access_token_expire_minutes <= 0:
            raise ValueError("access_token_expire_minutes must be positive")


@dataclass(frozen=True)
class RepositoryConfig:
    """Configuration for repository operations."""

    query_timeout_seconds: int = 30
    max_retries: int = 3
