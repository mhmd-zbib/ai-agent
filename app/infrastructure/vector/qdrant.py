"""
Qdrant vector client — self-hosted alternative to Pinecone.

Key design decisions
--------------------
Single collection
    All documents live in one collection regardless of tenant.
    Pinecone uses a namespace per tenant; Qdrant achieves the same with a
    ``user_id`` payload field that is included in every filter at query /
    delete time.

String → UUID point IDs
    Qdrant requires point IDs to be unsigned integers or UUIDs.
    Our chunk IDs are strings (``{document_id}_chunk_{n:06d}``).
    We deterministically map them to UUID5 values so the mapping is stable
    and reversible; the original string is stored in the payload as
    ``_chunk_id`` so callers always see the logical ID.

Lazy collection creation
    The collection is created on first use (idempotent, double-checked
    with a lock) — same pattern as the Pinecone client.
"""

import uuid
from threading import Lock

from app.infrastructure.vector.base import IVectorClient, VectorRecord
from app.shared.logging import get_logger

logger = get_logger(__name__)

# Deterministic UUID namespace for chunk_id → UUID5 mapping
_UUID_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_UUID_NS, chunk_id))


class QdrantVectorClient:
    """
    Qdrant implementation of IVectorClient.

    Args:
        host:            Qdrant server hostname (default ``localhost``).
        port:            Qdrant REST port (default 6333).
        collection_name: Collection to store all vectors in.
        dimension:       Vector dimensionality — must match the embedding model.
        metric:          Distance metric: ``cosine``, ``euclidean``, or ``dot``.
    """

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = "agent-documents",
        dimension: int,
        metric: str = "cosine",
    ) -> None:
        from qdrant_client import QdrantClient

        self._client = QdrantClient(host=host, port=port)
        self._collection = collection_name
        self._dimension = dimension
        self._metric = metric
        self._ready = False
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_collection(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            from qdrant_client.models import Distance, VectorParams

            distance = {
                "cosine": Distance.COSINE,
                "euclidean": Distance.EUCLID,
                "dot": Distance.DOT,
            }.get(self._metric.lower(), Distance.COSINE)

            if not self._client.collection_exists(self._collection):
                self._client.create_collection(
                    collection_name=self._collection,
                    vectors_config=VectorParams(size=self._dimension, distance=distance),
                )
                logger.info(
                    "Qdrant collection created",
                    extra={
                        "collection": self._collection,
                        "dimension": self._dimension,
                        "metric": self._metric,
                    },
                )
            else:
                logger.info(
                    "Qdrant collection ready", extra={"collection": self._collection}
                )

            self._ready = True

    def _namespace_filter(self, namespace: str):
        """Return a Qdrant Filter that restricts results to *namespace* (user_id)."""
        if not namespace:
            return None
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        return Filter(
            must=[FieldCondition(key="user_id", match=MatchValue(value=namespace))]
        )

    # ------------------------------------------------------------------
    # IVectorClient implementation
    # ------------------------------------------------------------------

    def upsert_records(self, records: list[VectorRecord], namespace: str = "") -> None:
        if not records:
            return
        self._ensure_collection()
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=_point_id(r["id"]),
                vector=r["values"],
                # Store original string ID so query results carry the logical ID
                payload={**r["metadata"], "_chunk_id": r["id"]},
            )
            for r in records
        ]
        try:
            self._client.upsert(collection_name=self._collection, points=points)
        except Exception as exc:
            # Collection deleted externally while the client was running.
            # Reset the ready flag and recreate, then retry once.
            if "doesn't exist" in str(exc) or "Not found" in str(exc):
                logger.warning(
                    "Qdrant collection missing — recreating and retrying",
                    extra={"collection": self._collection},
                )
                self._ready = False
                self._ensure_collection()
                self._client.upsert(collection_name=self._collection, points=points)
            else:
                raise

    def query(
        self,
        *,
        vector: list[float],
        top_k: int = 10,
        namespace: str = "",
        filter: dict | None = None,
    ) -> list[dict]:
        self._ensure_collection()
        response = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=top_k,
            query_filter=self._namespace_filter(namespace),
            with_payload=True,
        )
        return [
            {
                "id": (hit.payload or {}).get("_chunk_id", str(hit.id)),
                "score": hit.score,
                "metadata": {k: v for k, v in (hit.payload or {}).items() if k != "_chunk_id"},
            }
            for hit in response.points
        ]

    def delete(self, *, vector_ids: list[str], namespace: str = "") -> None:
        if not vector_ids:
            return
        self._ensure_collection()
        from qdrant_client.models import PointIdsList

        self._client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=[_point_id(vid) for vid in vector_ids]),
        )

    def close(self) -> None:
        self._client.close()
