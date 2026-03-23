from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    """Configuration for memory caching and pagination."""

    # Short-term cache settings
    redis_ttl_seconds: int = 3600
    max_cached_sessions: int = 1000

    # Long-term query settings
    query_timeout_seconds: int = 30
    default_page_size: int = 100
    max_page_size: int = 1000
