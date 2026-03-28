from typing import Any, Protocol, TypedDict

from .schemas import MemoryEntry, SessionState

# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class IMemoryService(Protocol):
    def get_session_state(self, session_id: str) -> SessionState: ...
    def append_message(self, session_id: str, entry: MemoryEntry) -> None: ...
    def clear_session(self, session_id: str) -> bool: ...
    def close(self) -> None: ...
    def get_metadata(self, session_id: str, key: str) -> str: ...
    def set_metadata(self, session_id: str, key: str, value: str) -> None: ...
    def delete_metadata(self, session_id: str, key: str) -> None: ...


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


class IToolRegistry(Protocol):
    def resolve(self, tool_id: str) -> Any: ...
    def get_tools_for_openai(self) -> list[dict[str, object]]: ...
    def list_tools(self) -> list[str]: ...


# ---------------------------------------------------------------------------
# Vector store (cross-cutting — used by rag/)
# ---------------------------------------------------------------------------


class VectorRecord(TypedDict):
    """Wire format passed to upsert_records across all vector backends."""

    id: str
    values: list[float]
    metadata: dict


class IVectorClient(Protocol):
    """Port implemented by Qdrant, Pinecone, or any other vector backend."""

    def upsert_records(self, records: list, namespace: str = "") -> None: ...

    def query(
        self,
        *,
        vector: list[float],
        top_k: int = 10,
        namespace: str = "",
        filter: dict | None = None,
    ) -> list[dict]: ...

    def delete(self, *, vector_ids: list[str], namespace: str = "") -> None: ...

    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Embedding (cross-cutting — used by rag/)
# ---------------------------------------------------------------------------


class IEmbeddingClient(Protocol):
    """Port implemented by OpenAI, Ollama, or any other embedding provider."""

    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
