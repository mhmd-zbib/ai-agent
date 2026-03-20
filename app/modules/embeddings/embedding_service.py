"""
Service for generating text embeddings using OpenAI's embedding API.

Implements Cache-Aside, Decorator, and Strategy patterns for robust caching
and error handling.
"""

import time
from typing import Final

from openai import OpenAI, OpenAIError, RateLimitError, APIError

from app.shared.exceptions import ConfigurationError, UpstreamServiceError
from app.shared.logging import get_logger
from app.modules.embeddings.cache_strategy import (
    CacheStrategy,
    LRUCacheStrategy,
    NoOpCacheStrategy,
    CacheStatistics,
)
from app.modules.embeddings.config import EmbeddingConfig

logger = get_logger(__name__)

# Constants for validation
MIN_TEXT_LENGTH: Final[int] = 1
MAX_TEXT_LENGTH_DEFAULT: Final[int] = 8192


class EmbeddingService:
    """
    Service for generating text embeddings using OpenAI's embedding API.

    Features:
    - LRU cache with configurable size to prevent memory leaks
    - Batch processing with size limits to avoid OOM
    - Automatic retry logic with exponential backoff
    - Cache hit rate monitoring
    - Strategy pattern for flexible caching strategies

    Example:
        >>> config = EmbeddingConfig(cache_max_size=500)
        >>> service = EmbeddingService(api_key="sk-...", config=config)
        >>> embedding = service.generate_embedding("Hello world")
        >>> stats = service.get_cache_statistics()
        >>> print(f"Hit rate: {stats.hit_rate}%")
    """

    def __init__(
        self,
        api_key: str | None,
        model: str = "text-embedding-3-small",
        base_url: str | None = None,
        config: EmbeddingConfig | None = None,
        cache_strategy: CacheStrategy[str, list[float]] | None = None,
    ) -> None:
        """
        Initialize the embedding service.

        Args:
            api_key: OpenAI API key. If None, raises ConfigurationError on first use.
            model: Name of the OpenAI embedding model to use.
            base_url: Optional custom base URL for OpenAI API.
            config: Configuration object. If None, uses defaults.
            cache_strategy: Custom cache strategy. If None, uses LRU cache.

        Raises:
            ConfigurationError: If api_key is None when attempting to generate embeddings.
        """
        # Initialize OpenAI client
        if api_key:
            client_kwargs = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            self._client: OpenAI | None = OpenAI(**client_kwargs)
        else:
            self._client = None

        # Configuration
        self._config = config or EmbeddingConfig(model=model, base_url=base_url)

        # Cache strategy (Strategy Pattern)
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
                "model": self._config.model,
                "has_client": self._client is not None,
                "base_url": self._config.base_url,
                "cache_max_size": self._config.cache_max_size,
                "cache_enabled": self._config.cache_enabled,
                "max_batch_size": self._config.max_batch_size,
            },
        )

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate an embedding vector for a single text.

        Implements Cache-Aside pattern: check cache first, then fetch and store.

        Args:
            text: The text to generate an embedding for.

        Returns:
            A list of floats representing the embedding vector.

        Raises:
            ConfigurationError: If the OpenAI API key is not configured.
            UpstreamServiceError: If the OpenAI API fails after all retry attempts.
            ValueError: If the input text is empty, whitespace only, or too long.
        """
        # Validate input
        self._validate_text(text)

        if self._client is None:
            raise ConfigurationError(
                "OPENAI_API_KEY is required to use the embedding service."
            )

        # Cache-Aside Pattern: Check cache first
        cache_key = self._normalize_text(text)
        cached_embedding = self._cache.get(cache_key)

        if cached_embedding is not None:
            logger.debug(
                "Cache hit for embedding",
                extra={
                    "text_length": len(cache_key),
                    "cache_size": self._cache.size(),
                },
            )
            return cached_embedding

        logger.debug(
            "Cache miss for embedding",
            extra={
                "text_length": len(cache_key),
                "cache_size": self._cache.size(),
            },
        )

        # Fetch from API with retry logic
        embedding = self._fetch_embedding_with_retry(cache_key)

        # Cache-Aside Pattern: Store in cache
        self._cache.set(cache_key, embedding)

        # Log cache statistics periodically
        if self._config.enable_cache_stats:
            self._log_cache_stats()

        return embedding

    def _validate_text(self, text: str) -> None:
        """
        Validate input text.

        Args:
            text: Text to validate.

        Raises:
            ValueError: If text is invalid.
        """
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty or whitespace only")

        if len(text) > self._config.max_text_length:
            raise ValueError(
                f"Text length ({len(text)}) exceeds maximum "
                f"({self._config.max_text_length})"
            )

    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for cache key.

        Args:
            text: Text to normalize.

        Returns:
            Normalized text.
        """
        return text.strip()

    def _fetch_embedding_with_retry(self, text: str) -> list[float]:
        """
        Fetch embedding from API with retry logic.

        Args:
            text: Normalized text to embed.

        Returns:
            Embedding vector.

        Raises:
            UpstreamServiceError: If API fails after all retries.
        """
        last_error: Exception | None = None

        for attempt in range(self._config.max_retries):
            try:
                logger.debug(
                    "Requesting embedding from OpenAI",
                    extra={
                        "model": self._config.model,
                        "text_length": len(text),
                        "attempt": attempt + 1,
                    },
                )

                response = self._client.embeddings.create(  # type: ignore
                    model=self._config.model,
                    input=text,
                )

                embedding = response.data[0].embedding

                logger.debug(
                    "Successfully generated embedding",
                    extra={
                        "embedding_dimensions": len(embedding),
                        "attempt": attempt + 1,
                    },
                )

                return embedding

            except RateLimitError as e:
                last_error = e
                self._handle_retry(e, attempt, "Rate limit")

            except APIError as e:
                last_error = e
                self._handle_retry(e, attempt, "API error")

            except OpenAIError as e:
                logger.error(
                    "OpenAI error during embedding generation",
                    extra={"error": str(e)},
                )
                raise UpstreamServiceError(
                    f"Failed to generate embedding from OpenAI: {e}"
                ) from e

            except Exception as e:
                logger.error(
                    "Unexpected error calling OpenAI embeddings API",
                    extra={"error": str(e)},
                )
                raise UpstreamServiceError(
                    f"Unexpected error generating embedding: {e}"
                ) from e

        # All retries exhausted
        raise UpstreamServiceError(
            f"Failed to generate embedding after {self._config.max_retries} attempts"
        ) from last_error

    def _handle_retry(
        self, error: Exception, attempt: int, error_type: str
    ) -> None:
        """
        Handle retry logic with exponential backoff.

        Args:
            error: The error that occurred.
            attempt: Current attempt number (0-indexed).
            error_type: Description of error type for logging.

        Raises:
            UpstreamServiceError: If this was the last retry attempt.
        """
        if attempt < self._config.max_retries - 1:
            wait_time = self._config.retry_delay_seconds * (2**attempt)
            logger.warning(
                f"{error_type} on attempt {attempt + 1}/{self._config.max_retries}",
                extra={
                    "error": str(error),
                    "attempt": attempt + 1,
                    "wait_seconds": wait_time,
                },
            )
            time.sleep(wait_time)
        else:
            logger.error(
                f"{error_type} after all retry attempts",
                extra={"error": str(error)},
            )
            raise UpstreamServiceError(
                f"OpenAI {error_type.lower()} after {self._config.max_retries} attempts"
            ) from error

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for multiple texts in batches.

        Implements batch processing with size limits to prevent OOM.
        Uses Cache-Aside pattern for efficient batch caching.

        Args:
            texts: A list of texts to generate embeddings for.

        Returns:
            A list of embedding vectors, one for each input text.

        Raises:
            ConfigurationError: If the OpenAI API key is not configured.
            UpstreamServiceError: If the OpenAI API fails after all retry attempts.
            ValueError: If the texts list is empty or contains only whitespace strings.
        """
        if not texts:
            raise ValueError("Input texts list cannot be empty")

        if self._client is None:
            raise ConfigurationError(
                "OPENAI_API_KEY is required to use the embedding service."
            )

        # Validate and normalize texts
        valid_texts, valid_indices = self._validate_and_normalize_batch(texts)

        if not valid_texts:
            raise ValueError("All input texts are empty or whitespace only")

        # Check batch size limit
        if len(valid_texts) > self._config.max_batch_size:
            return self._process_large_batch(valid_texts)

        # Cache-Aside Pattern: Check cache and identify texts to fetch
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

        # If all embeddings are cached, return them
        if not texts_to_fetch:
            logger.debug("All embeddings found in cache")
            return [cached_embeddings[i] for i in range(len(valid_texts))]

        # Fetch uncached embeddings from API
        new_embeddings = self._fetch_batch_with_retry(texts_to_fetch)

        # Cache new embeddings
        for text, embedding in zip(texts_to_fetch, new_embeddings):
            self._cache.set(text, embedding)

        # Combine cached and new embeddings in original order
        return self._combine_batch_results(
            valid_texts, cached_embeddings, new_embeddings, fetch_indices
        )

    def _validate_and_normalize_batch(
        self, texts: list[str]
    ) -> tuple[list[str], list[int]]:
        """
        Validate and normalize batch of texts.

        Args:
            texts: Raw text inputs.

        Returns:
            Tuple of (valid normalized texts, their original indices).
        """
        valid_texts: list[str] = []
        valid_indices: list[int] = []

        for i, text in enumerate(texts):
            if text and text.strip():
                normalized = self._normalize_text(text)

                # Check text length
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
        """
        Check cache for batch texts.

        Args:
            texts: Normalized texts to check.

        Returns:
            Tuple of (cached embeddings by index, texts to fetch, fetch indices).
        """
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
        """
        Fetch batch embeddings from API with retry logic.

        Args:
            texts: Texts to fetch embeddings for.

        Returns:
            List of embedding vectors.

        Raises:
            UpstreamServiceError: If API fails after all retries.
        """
        last_error: Exception | None = None

        for attempt in range(self._config.max_retries):
            try:
                logger.debug(
                    "Requesting batch embeddings from OpenAI",
                    extra={
                        "model": self._config.model,
                        "batch_size": len(texts),
                        "attempt": attempt + 1,
                    },
                )

                response = self._client.embeddings.create(  # type: ignore
                    model=self._config.model,
                    input=texts,
                )

                embeddings = [item.embedding for item in response.data]

                logger.debug(
                    "Successfully generated batch embeddings",
                    extra={
                        "embedding_count": len(embeddings),
                        "embedding_dimensions": (
                            len(embeddings[0]) if embeddings else 0
                        ),
                        "attempt": attempt + 1,
                    },
                )

                return embeddings

            except RateLimitError as e:
                last_error = e
                self._handle_retry(e, attempt, "Rate limit")

            except APIError as e:
                last_error = e
                self._handle_retry(e, attempt, "API error")

            except OpenAIError as e:
                logger.error(
                    "OpenAI error during batch embedding generation",
                    extra={"error": str(e)},
                )
                raise UpstreamServiceError(
                    f"Failed to generate batch embeddings from OpenAI: {e}"
                ) from e

            except Exception as e:
                logger.error(
                    "Unexpected error calling OpenAI batch embeddings API",
                    extra={"error": str(e)},
                )
                raise UpstreamServiceError(
                    f"Unexpected error generating batch embeddings: {e}"
                ) from e

        raise UpstreamServiceError(
            f"Failed to generate batch embeddings after {self._config.max_retries} attempts"
        ) from last_error

    def _process_large_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Process large batch by splitting into smaller chunks.

        Args:
            texts: Large list of texts to process.

        Returns:
            List of all embedding vectors.
        """
        logger.info(
            "Processing large batch in chunks",
            extra={
                "total_size": len(texts),
                "chunk_size": self._config.max_batch_size,
            },
        )

        all_embeddings: list[list[float]] = []
        chunk_size = self._config.max_batch_size

        for i in range(0, len(texts), chunk_size):
            chunk = texts[i : i + chunk_size]
            chunk_embeddings = self.generate_embeddings_batch(chunk)
            all_embeddings.extend(chunk_embeddings)

        return all_embeddings

    def _combine_batch_results(
        self,
        valid_texts: list[str],
        cached_embeddings: dict[int, list[float]],
        new_embeddings: list[list[float]],
        fetch_indices: list[int],
    ) -> list[list[float]]:
        """
        Combine cached and newly fetched embeddings in original order.

        Args:
            valid_texts: All valid texts in order.
            cached_embeddings: Cached embeddings by index.
            new_embeddings: Newly fetched embeddings.
            fetch_indices: Indices of texts that were fetched.

        Returns:
            Combined list of embeddings in original order.
        """
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
        logger.info(
            "Cleared embedding cache",
            extra={"cleared_items": cache_size},
        )

    def get_cache_size(self) -> int:
        """
        Get the number of cached embeddings.

        Returns:
            The number of entries in the cache.
        """
        return self._cache.size()

    def get_cache_statistics(self) -> CacheStatistics:
        """
        Get cache performance statistics.

        Returns:
            CacheStatistics object with hit rate, misses, evictions, etc.
        """
        return self._cache.get_statistics()

    def reset_cache_statistics(self) -> None:
        """Reset cache statistics counters."""
        self._cache.reset_statistics()
        logger.info("Reset cache statistics")

    def _log_cache_stats(self) -> None:
        """Log cache statistics periodically."""
        stats = self._cache.get_statistics()

        # Log every 100 requests to avoid spam
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
