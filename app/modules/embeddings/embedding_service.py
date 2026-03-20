from typing import Optional
from openai import OpenAI, OpenAIError, RateLimitError, APIError
from app.shared.exceptions import ConfigurationError, UpstreamServiceError
from app.shared.logging import get_logger

logger = get_logger(__name__)


class EmbeddingService:
    """
    Service for generating text embeddings using OpenAI's embedding API.
    
    Supports both single text and batch processing with automatic retry logic
    for handling transient failures and rate limits.
    """

    def __init__(
        self,
        api_key: str | None,
        model: str = "text-embedding-3-small",
        base_url: str | None = None,
    ) -> None:
        """
        Initialize the embedding service.

        Args:
            api_key: OpenAI API key. If None, raises ConfigurationError on first use.
            model: Name of the OpenAI embedding model to use.
            base_url: Optional custom base URL for OpenAI API.

        Raises:
            ConfigurationError: If api_key is None when attempting to generate embeddings.
        """
        if api_key:
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self._client: Optional[OpenAI] = OpenAI(**kwargs)
        else:
            self._client = None

        self._model = model
        self._embedding_cache: dict[str, list[float]] = {}

        logger.info(
            "Initialized EmbeddingService",
            extra={
                "model": self._model,
                "has_client": self._client is not None,
                "base_url": base_url,
            },
        )

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generate an embedding vector for a single text.

        Args:
            text: The text to generate an embedding for.

        Returns:
            A list of floats representing the embedding vector.

        Raises:
            ConfigurationError: If the OpenAI API key is not configured.
            UpstreamServiceError: If the OpenAI API fails after all retry attempts.
            ValueError: If the input text is empty or whitespace only.
        """
        if not text or not text.strip():
            raise ValueError("Input text cannot be empty or whitespace only")

        if self._client is None:
            raise ConfigurationError(
                "OPENAI_API_KEY is required to use the embedding service."
            )

        # Check cache first
        cache_key = text.strip()
        if cache_key in self._embedding_cache:
            logger.debug(
                "Returning cached embedding",
                extra={"text_length": len(cache_key)},
            )
            return self._embedding_cache[cache_key]

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                logger.debug(
                    "Requesting embedding from OpenAI",
                    extra={
                        "model": self._model,
                        "text_length": len(text),
                        "attempt": attempt + 1,
                    },
                )

                response = self._client.embeddings.create(
                    model=self._model,
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

                # Cache the result
                self._embedding_cache[cache_key] = embedding

                return embedding

            except RateLimitError as e:
                last_error = e
                logger.warning(
                    f"Rate limit hit on attempt {attempt + 1}/{max_retries}",
                    extra={
                        "error": str(e),
                        "attempt": attempt + 1,
                    },
                )
                if attempt < max_retries - 1:
                    continue
                else:
                    logger.error(
                        "Rate limit exceeded after all retry attempts",
                        extra={"error": str(last_error)},
                    )
                    raise UpstreamServiceError(
                        f"OpenAI rate limit exceeded after {max_retries} attempts"
                    ) from last_error

            except APIError as e:
                last_error = e
                logger.warning(
                    f"API error on attempt {attempt + 1}/{max_retries}",
                    extra={
                        "error": str(e),
                        "attempt": attempt + 1,
                    },
                )
                if attempt < max_retries - 1:
                    continue
                else:
                    logger.error(
                        "API error after all retry attempts",
                        extra={"error": str(last_error)},
                    )
                    raise UpstreamServiceError(
                        f"OpenAI API error after {max_retries} attempts: {last_error}"
                    ) from last_error

            except OpenAIError as e:
                last_error = e
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

        # This should never be reached due to the exception handling above,
        # but included for completeness
        raise UpstreamServiceError(
            f"Failed to generate embedding after {max_retries} attempts"
        )

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embedding vectors for multiple texts in a single batch request.

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

        # Filter out empty/whitespace texts and track original indices
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text.strip())
                valid_indices.append(i)

        if not valid_texts:
            raise ValueError("All input texts are empty or whitespace only")

        if self._client is None:
            raise ConfigurationError(
                "OPENAI_API_KEY is required to use the embedding service."
            )

        # Check cache and identify texts that need to be fetched
        cached_embeddings: dict[int, list[float]] = {}
        texts_to_fetch = []
        fetch_indices = []

        for i, text in enumerate(valid_texts):
            if text in self._embedding_cache:
                cached_embeddings[i] = self._embedding_cache[text]
            else:
                texts_to_fetch.append(text)
                fetch_indices.append(i)

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

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                logger.debug(
                    "Requesting batch embeddings from OpenAI",
                    extra={
                        "model": self._model,
                        "batch_size": len(texts_to_fetch),
                        "attempt": attempt + 1,
                    },
                )

                response = self._client.embeddings.create(
                    model=self._model,
                    input=texts_to_fetch,
                )

                # Extract embeddings and maintain order
                new_embeddings = [item.embedding for item in response.data]

                logger.debug(
                    "Successfully generated batch embeddings",
                    extra={
                        "embedding_count": len(new_embeddings),
                        "embedding_dimensions": len(new_embeddings[0]) if new_embeddings else 0,
                        "attempt": attempt + 1,
                    },
                )

                # Cache the new embeddings
                for text, embedding in zip(texts_to_fetch, new_embeddings):
                    self._embedding_cache[text] = embedding

                # Combine cached and new embeddings in original order
                all_embeddings: list[list[float]] = []
                for i in range(len(valid_texts)):
                    if i in cached_embeddings:
                        all_embeddings.append(cached_embeddings[i])
                    else:
                        fetch_position = fetch_indices.index(i)
                        all_embeddings.append(new_embeddings[fetch_position])

                return all_embeddings

            except RateLimitError as e:
                last_error = e
                logger.warning(
                    f"Rate limit hit on batch attempt {attempt + 1}/{max_retries}",
                    extra={
                        "error": str(e),
                        "attempt": attempt + 1,
                        "batch_size": len(texts_to_fetch),
                    },
                )
                if attempt < max_retries - 1:
                    continue
                else:
                    logger.error(
                        "Rate limit exceeded after all retry attempts",
                        extra={"error": str(last_error)},
                    )
                    raise UpstreamServiceError(
                        f"OpenAI rate limit exceeded after {max_retries} attempts"
                    ) from last_error

            except APIError as e:
                last_error = e
                logger.warning(
                    f"API error on batch attempt {attempt + 1}/{max_retries}",
                    extra={
                        "error": str(e),
                        "attempt": attempt + 1,
                        "batch_size": len(texts_to_fetch),
                    },
                )
                if attempt < max_retries - 1:
                    continue
                else:
                    logger.error(
                        "API error after all retry attempts",
                        extra={"error": str(last_error)},
                    )
                    raise UpstreamServiceError(
                        f"OpenAI API error after {max_retries} attempts: {last_error}"
                    ) from last_error

            except OpenAIError as e:
                last_error = e
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
            f"Failed to generate batch embeddings after {max_retries} attempts"
        )

    def clear_cache(self) -> None:
        """Clear the internal embedding cache."""
        cache_size = len(self._embedding_cache)
        self._embedding_cache.clear()
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
        return len(self._embedding_cache)
