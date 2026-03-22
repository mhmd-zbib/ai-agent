"""
Tests for EmbeddingService with the IEmbeddingClient port.

Verifies that:
- EmbeddingService delegates embed() calls to the injected client
- EmbeddingService delegates embed_batch() calls to the injected client
- Cache hits avoid calling the client at all
- ConfigurationError is raised when no client is provided
- OpenAIEmbeddingClient satisfies IEmbeddingClient (has embed + embed_batch)
"""
import pytest

from app.shared.protocols import IEmbeddingClient
from app.infrastructure.embedding.openai import OpenAIEmbeddingClient
from app.modules.embeddings.config import EmbeddingConfig
from app.modules.embeddings.embedding_service import EmbeddingService
from app.shared.exceptions import ConfigurationError


# ---------------------------------------------------------------------------
# Fake IEmbeddingClient — no inheritance from OpenAIEmbeddingClient
# ---------------------------------------------------------------------------

class _FakeEmbeddingClient:
    """In-memory embedding client that satisfies IEmbeddingClient by duck typing."""

    def __init__(self, dim: int = 4) -> None:
        self._dim = dim
        self.embed_calls: list[str] = []
        self.batch_calls: list[list[str]] = []

    def embed(self, text: str) -> list[float]:
        self.embed_calls.append(text)
        return [float(i) for i in range(self._dim)]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls.append(list(texts))
        return [[float(i) for i in range(self._dim)] for _ in texts]


# ---------------------------------------------------------------------------
# Basic delegation tests
# ---------------------------------------------------------------------------

def test_generate_embedding_delegates_to_client() -> None:
    client = _FakeEmbeddingClient(dim=3)
    service = EmbeddingService(client=client, config=EmbeddingConfig(cache_enabled=False))

    vector = service.generate_embedding("hello world")

    assert client.embed_calls == ["hello world"]
    assert len(vector) == 3


def test_generate_embedding_batch_delegates_to_client() -> None:
    client = _FakeEmbeddingClient(dim=3)
    service = EmbeddingService(client=client, config=EmbeddingConfig(cache_enabled=False))

    vectors = service.generate_embeddings_batch(["text one", "text two"])

    assert client.batch_calls == [["text one", "text two"]]
    assert len(vectors) == 2
    assert all(len(v) == 3 for v in vectors)


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------

def test_cache_hit_avoids_client_call() -> None:
    client = _FakeEmbeddingClient()
    service = EmbeddingService(client=client, config=EmbeddingConfig(cache_enabled=True))

    # First call — cache miss
    service.generate_embedding("cached text")
    # Second call — cache hit, client should NOT be called again
    service.generate_embedding("cached text")

    assert len(client.embed_calls) == 1


def test_cache_size_reflects_stored_embeddings() -> None:
    client = _FakeEmbeddingClient()
    service = EmbeddingService(client=client, config=EmbeddingConfig(cache_enabled=True))

    service.generate_embedding("text a")
    service.generate_embedding("text b")

    assert service.get_cache_size() == 2


def test_clear_cache_resets_size() -> None:
    client = _FakeEmbeddingClient()
    service = EmbeddingService(client=client, config=EmbeddingConfig(cache_enabled=True))

    service.generate_embedding("something")
    service.clear_cache()

    assert service.get_cache_size() == 0


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_generate_embedding_raises_when_no_client() -> None:
    service = EmbeddingService(client=None, config=EmbeddingConfig(cache_enabled=False))

    with pytest.raises(ConfigurationError):
        service.generate_embedding("text")


def test_generate_batch_raises_when_no_client() -> None:
    service = EmbeddingService(client=None, config=EmbeddingConfig(cache_enabled=False))

    with pytest.raises(ConfigurationError):
        service.generate_embeddings_batch(["text"])


def test_generate_embedding_raises_for_empty_text() -> None:
    client = _FakeEmbeddingClient()
    service = EmbeddingService(client=client)

    with pytest.raises(ValueError, match="empty"):
        service.generate_embedding("   ")


def test_generate_batch_raises_for_empty_list() -> None:
    client = _FakeEmbeddingClient()
    service = EmbeddingService(client=client)

    with pytest.raises(ValueError):
        service.generate_embeddings_batch([])


# ---------------------------------------------------------------------------
# IEmbeddingClient structural check
# ---------------------------------------------------------------------------

def test_iembedding_client_protocol_interface() -> None:
    """Structural check: our fake satisfies the protocol without any base class."""
    client: IEmbeddingClient = _FakeEmbeddingClient()
    vec = client.embed("test")
    assert isinstance(vec, list)
    vecs = client.embed_batch(["a", "b"])
    assert len(vecs) == 2


def test_openai_embedding_client_has_embed_batch_method() -> None:
    """OpenAIEmbeddingClient must now expose embed_batch to satisfy IEmbeddingClient."""
    client = OpenAIEmbeddingClient(api_key="sk-test", model="text-embedding-3-small")
    assert callable(getattr(client, "embed_batch", None))
