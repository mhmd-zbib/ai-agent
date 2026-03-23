"""
Service for generating text embeddings.

Delegates all API calls to an IEmbeddingClient, keeping this service
focused on caching, batching, validation, and cache statistics.
"""

from typing import Final

from app.shared.protocols import IEmbeddingClient
from app.shared.exceptions import ConfigurationError
from app.shared.logging import get_logger
from app.modules.embeddings.cache_strategy import (
    CacheStrategy,
    LRUCacheStrategy,
    NoOpCacheStrategy,
    CacheStatistics,
)
from app.modules.embeddings.config import EmbeddingConfig

logger = get_logger(__name__)

MIN_TEXT_LENGTH: Final[int] = 1
MAX_TEXT_LENGTH_DEFAULT: Final[int] = 8192


class EmbeddingService:
    """
    Service for generating text embeddings.

    Features:
    - LRU cache with configurable size to prevent memory leaks
    - Batch processing with size limits to avoid OOM
    - Cache hit rate monitoring
    - Strategy pattern for flexible caching strategies

    Example:
        >>> from app.infrastructure.embedding.openai import OpenAIEmbeddingClient
        >>> client = OpenAIEmbeddingClient(api_key="sk-...")
        >>> service = EmbeddingService(client=client)
        >>> embedding = service.generate_embedding("Hello world")
        >>> stats = service.get_cache_statistics()
        >>> print(f"Hit rate: {stats.hit_rate}%")
    """

    def __init__(
        self,
        client: IEmbeddingClient | None = None,
        config: EmbeddingConfig | None = None,
        cache_strategy: CacheStrategy[str, list[float]] | None = None,
    ) -> None:
        """
        Initialize the embedding service.

        Args:
            client: Embedding client implementing IEmbeddingClient.
                    If None, raises ConfigurationError on first use.
            config: Configuration object. If None, uses defaults.
            cache_strategy: Custom cache strategy. If None, uses LRU cache.
        """
        self._client = client
        self._config = config or EmbeddingConfig()

        if cache_strategy:
            self._cache = cache_strategy
        elif self._config.cache_enabled:
            self._cache = LRUCacheStrategy[str, list[float]](
                max_size=self._config.cache_max_size
            )
        else:
            self._cache = NoOpCacheStrategy[str, list[float]]()

        logger.info(
            "Initialized EmbeddingService",
            extra={
                "has_client": self._client is not None,
                "cache_max_size": self._config.cache_max_size,
                "cache_enabled": self._config.cache_enabled,
                "max_batch_size": self._config.max_batch_size,
            },
        )

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate an embedding vector for a single text.

        Implements Cache-Aside pattern: check cache first, then fetch and store.

        Raises:
            ConfigurationError: If no embedding client was provided.
            ValueError: If the input text is empty, whitespace only, or too long.
        """
        self._validate_text(text)

        if self._client is None:
            raise ConfigurationError(
                "An IEmbeddingClient is required to use the embedding service."
            )

        cache_key = self._normalize_text(text)
        cached_embedding = self._cache.get(cache_key)

        if cached_embedding is not None:
            logger.debug(
                "Cache hit for embedding",
                extra={"text_length": len(cache_key), "cache_size": self._cache.size()},
            )
            return cached_embedding

        logger.debug(
            "Cache miss for embedding",
            extra={"text_length": len(cache_key), "cache_size": self._cache.size()},
        )

        embedding = self._fetch_embedding_with_retry(cache_key)
        self._cache.set(cache_key, embedding)

        if self._config.enable_cache_stats:
            self._log_cache_stats()

        return embedding

    def _validate_text(self, text: str) -> None:
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty or whitespace only")
        if len(text) > self._config.max_text_length:
            raise ValueError(
                f"Text length ({len(text)}) exceeds maximum ({self._config.max_text_length})"
            )

    def _normalize_text(self, text: str) -> str:
        return text.strip()

    def _fetch_embedding_with_retry(self, text: str) -> list[float]:
        assert self._client is not None
        return self._client.embed(text)

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for multiple texts in batches.

        Implements batch processing with size limits to prevent OOM.
        Uses Cache-Aside pattern for efficient batch caching.

        Raises:
            ConfigurationError: If no embedding client was provided.
            ValueError: If the texts list is empty or all items are whitespace.
        """
        if not texts:
            raise ValueError("Input texts list cannot be empty")

        if self._client is None:
            raise ConfigurationError(
                "An IEmbeddingClient is required to use the embedding service."
            )

        valid_texts, valid_indices = self._validate_and_normalize_batch(texts)

        if not valid_texts:
            raise ValueError("All input texts are empty or whitespace only")

        if len(valid_texts) > self._config.max_batch_size:
            return self._process_large_batch(valid_texts)

        cached_embeddings, texts_to_fetch, fetch_indices = self._check_batch_cache(
            valid_texts
        )

        logger.debug(
            "Processing batch embedding request",
            extra={
                "total_texts": len(texts),
                "valid_texts": len(valid_texts),
                "cached_count": len(cached_embeddings),
                "to_fetch": len(texts_to_fetch),
            },
        )

        if not texts_to_fetch:
            logger.debug("All embeddings found in cache")
            return [cached_embeddings[i] for i in range(len(valid_texts))]

        new_embeddings = self._fetch_batch_with_retry(texts_to_fetch)

        for text, embedding in zip(texts_to_fetch, new_embeddings):
            self._cache.set(text, embedding)

        return self._combine_batch_results(
            valid_texts, cached_embeddings, new_embeddings, fetch_indices
        )

    def _validate_and_normalize_batch(
        self, texts: list[str]
    ) -> tuple[list[str], list[int]]:
        valid_texts: list[str] = []
        valid_indices: list[int] = []

        for i, text in enumerate(texts):
            if text and text.strip():
                normalized = self._normalize_text(text)
                if len(normalized) > self._config.max_text_length:
                    logger.warning(
                        "Skipping text exceeding max length",
                        extra={
                            "index": i,
                            "length": len(normalized),
                            "max_length": self._config.max_text_length,
                        },
                    )
                    continue
                valid_texts.append(normalized)
                valid_indices.append(i)

        return valid_texts, valid_indices

    def _check_batch_cache(
        self, texts: list[str]
    ) -> tuple[dict[int, list[float]], list[str], list[int]]:
        cached_embeddings: dict[int, list[float]] = {}
        texts_to_fetch: list[str] = []
        fetch_indices: list[int] = []

        for i, text in enumerate(texts):
            cached = self._cache.get(text)
            if cached is not None:
                cached_embeddings[i] = cached
            else:
                texts_to_fetch.append(text)
                fetch_indices.append(i)

        return cached_embeddings, texts_to_fetch, fetch_indices

    def _fetch_batch_with_retry(self, texts: list[str]) -> list[list[float]]:
        assert self._client is not None
        return self._client.embed_batch(texts)

    def _process_large_batch(self, texts: list[str]) -> list[list[float]]:
        logger.info(
            "Processing large batch in chunks",
            extra={"total_size": len(texts), "chunk_size": self._config.max_batch_size},
        )

        all_embeddings: list[list[float]] = []
        chunk_size = self._config.max_batch_size

        for i in range(0, len(texts), chunk_size):
            chunk = texts[i : i + chunk_size]
            all_embeddings.extend(self.generate_embeddings_batch(chunk))

        return all_embeddings

    def _combine_batch_results(
        self,
        valid_texts: list[str],
        cached_embeddings: dict[int, list[float]],
        new_embeddings: list[list[float]],
        fetch_indices: list[int],
    ) -> list[list[float]]:
        all_embeddings: list[list[float]] = []

        for i in range(len(valid_texts)):
            if i in cached_embeddings:
                all_embeddings.append(cached_embeddings[i])
            else:
                fetch_position = fetch_indices.index(i)
                all_embeddings.append(new_embeddings[fetch_position])

        return all_embeddings

    def clear_cache(self) -> None:
        """Clear the internal embedding cache."""
        cache_size = self._cache.clear()
        logger.info("Cleared embedding cache", extra={"cleared_items": cache_size})

    def get_cache_size(self) -> int:
        return self._cache.size()

    def get_cache_statistics(self) -> CacheStatistics:
        return self._cache.get_statistics()

    def reset_cache_statistics(self) -> None:
        self._cache.reset_statistics()
        logger.info("Reset cache statistics")

    def _log_cache_stats(self) -> None:
        stats = self._cache.get_statistics()
        if stats.total_requests % 100 == 0:
            logger.info(
                "Cache statistics",
                extra={
                    "hit_rate": round(stats.hit_rate, 2),
                    "hits": stats.hits,
                    "misses": stats.misses,
                    "evictions": stats.evictions,
                    "cache_size": self._cache.size(),
                    "max_size": self._config.cache_max_size,
                },
            )
