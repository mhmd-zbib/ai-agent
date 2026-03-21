"""
Shared vector client protocol and types.

Both PineconeVectorClient and QdrantVectorClient implement IVectorClient.
Import VectorRecord and IVectorClient from here — never from a concrete module.
"""

from typing import Protocol, TypedDict


class VectorRecord(TypedDict):
    """Wire format passed to upsert_records across all backends."""

    id: str
    values: list[float]
    metadata: dict


class IVectorClient(Protocol):
    def upsert_records(self, records: list[VectorRecord], namespace: str = "") -> None: ...

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
