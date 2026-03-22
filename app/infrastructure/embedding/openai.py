"""
OpenAI (and OpenAI-compatible) embedding client.

Supports any OpenAI-compatible endpoint via *base_url* (Ollama, Azure, etc.)
and implements the IEmbeddingClient protocol defined in the pipeline services.
"""

import re
from typing import Any

from openai import APIStatusError, OpenAI, RateLimitError

from app.shared.logging import get_logger

logger = get_logger(__name__)

# Models that support the Matryoshka ``dimensions`` parameter
_MATRYOSHKA_PREFIXES = ("text-embedding-3-",)


def _normalize(text: str) -> str:
    """Collapse all whitespace to single spaces before embedding."""
    return re.sub(r"\s+", " ", text).strip()


def _supports_matryoshka(model: str) -> bool:
    return any(model.startswith(p) for p in _MATRYOSHKA_PREFIXES)


class OpenAIEmbeddingClient:
    """
    Embedding client backed by the OpenAI SDK.

    Compatible with any OpenAI-compatible endpoint via *base_url*.
    Implements the IEmbeddingClient protocol.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        base_url: str | None = None,
        dimensions: int | None = None,
        max_retries: int = 3,
    ) -> None:
        self._client = OpenAI(
            api_key=api_key,
            **({"base_url": base_url} if base_url else {}),
            max_retries=max_retries,
        )
        self._model = model
        self._dimensions: int | None = (
            dimensions if dimensions and _supports_matryoshka(model) else None
        )

    @property
    def model_name(self) -> str:
        return self._model

    def embed(self, text: str) -> list[float]:
        """Normalise *text*, call the embedding API, validate dimension, return vector."""
        normalised = _normalize(text)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": normalised,
            "encoding_format": "float",
        }
        if self._dimensions is not None:
            kwargs["dimensions"] = self._dimensions

        try:
            response = self._client.embeddings.create(**kwargs)
        except RateLimitError:
            logger.error(
                "Embedding API rate-limited — SDK will retry automatically",
                extra={"model": self._model},
            )
            raise
        except APIStatusError as exc:
            logger.error(
                "Embedding API error",
                extra={
                    "model": self._model,
                    "http_status": exc.status_code,
                    "error": exc.message,
                },
            )
            raise

        vector: list[float] = response.data[0].embedding

        if self._dimensions is not None and len(vector) != self._dimensions:
            raise ValueError(
                f"Dimension mismatch: expected {self._dimensions}, "
                f"got {len(vector)} from model '{self._model}'"
            )

        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Normalise *texts*, call the embedding API in one request, return vectors."""
        normalised = [_normalize(t) for t in texts]

        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": normalised,
            "encoding_format": "float",
        }
        if self._dimensions is not None:
            kwargs["dimensions"] = self._dimensions

        try:
            response = self._client.embeddings.create(**kwargs)
        except RateLimitError:
            logger.error(
                "Embedding API rate-limited — SDK will retry automatically",
                extra={"model": self._model},
            )
            raise
        except APIStatusError as exc:
            logger.error(
                "Embedding API error",
                extra={
                    "model": self._model,
                    "http_status": exc.status_code,
                    "error": exc.message,
                },
            )
            raise

        return [item.embedding for item in response.data]
