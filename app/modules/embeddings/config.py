"""
Configuration for embedding service.

Defines all configurable parameters for embeddings with sensible defaults.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingConfig:
    """Configuration for embedding service."""

    # Model settings
    model: str = "text-embedding-3-small"
    base_url: str | None = None

    # Cache settings
    cache_max_size: int = 1000
    cache_enabled: bool = True

    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: float = 1.0

    # Batch processing limits (prevent OOM)
    max_batch_size: int = 100
    max_text_length: int = 8192

    # Monitoring settings
    enable_cache_stats: bool = True

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.cache_max_size < 0:
            raise ValueError("cache_max_size must be non-negative")

        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")

        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")

        if self.max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")

        if self.max_text_length <= 0:
            raise ValueError("max_text_length must be positive")
