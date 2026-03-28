from dataclasses import dataclass


@dataclass(frozen=True)
class RepositoryConfig:
    """Configuration for user repository operations."""

    query_timeout_seconds: int = 30
    max_retries: int = 3
