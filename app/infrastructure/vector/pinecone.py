import time
from threading import Lock

from app.infrastructure.vector.base import VectorRecord  # noqa: F401 — re-exported
from app.shared.logging import get_logger

logger = get_logger(__name__)

# Pinecone metadata size limit is 40 KB per vector.
# 512-token chunks are ~2 000–4 000 chars — well within this.
_METADATA_TEXT_LIMIT = 10_000  # characters; safety cap


class PineconeVectorClient:
    """
    Pinecone client wrapper.

    Lazily initialises the index on first use.  If the index does not exist it
    is created as a serverless index using the configured cloud / region and
    the client blocks until Pinecone reports it as ``ready``.

    Thread-safe: lazy init is protected by a lock; the resulting
    ``Index`` object is safe to use from multiple threads simultaneously.
    """

    def __init__(
        self,
        *,
        api_key: str,
        index_name: str,
        dimension: int,
        metric: str = "cosine",
        cloud: str = "aws",
        region: str = "us-east-1",
    ) -> None:
        self._api_key = api_key
        self._index_name = index_name
        self._dimension = dimension
        self._metric = metric
        self._cloud = cloud
        self._region = region
        self._index = None
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_index(self) -> None:
        if self._index is not None:
            return

        with self._lock:
            if self._index is not None:
                return

            from pinecone import Pinecone, ServerlessSpec

            pc = Pinecone(api_key=self._api_key)
            existing_names = {idx.name for idx in pc.list_indexes()}

            if self._index_name not in existing_names:
                pc.create_index(
                    name=self._index_name,
                    dimension=self._dimension,
                    metric=self._metric,
                    spec=ServerlessSpec(cloud=self._cloud, region=self._region),
                )
                logger.info(
                    "Pinecone index created",
                    extra={
                        "index": self._index_name,
                        "dimension": self._dimension,
                        "metric": self._metric,
                    },
                )
                self._wait_until_ready(pc)

            self._index = pc.Index(self._index_name)
            logger.info("Pinecone index ready", extra={"index": self._index_name})

    def _wait_until_ready(
        self, pc, poll_interval: float = 1.0, timeout: float = 120.0
    ) -> None:
        """Block until the index status is ``ready`` or timeout is reached."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            desc = pc.describe_index(self._index_name)
            if desc.status.get("ready", False):
                return
            logger.debug(
                "Waiting for Pinecone index to become ready",
                extra={"index": self._index_name, "status": desc.status},
            )
            time.sleep(poll_interval)
        raise TimeoutError(
            f"Pinecone index '{self._index_name}' did not become ready "
            f"within {timeout}s"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert_records(
        self,
        records: list[VectorRecord],
        namespace: str = "",
    ) -> None:
        """
        Upsert a batch of vector records.

        Pinecone recommends batches of up to 100 vectors per request.
        Each record must have ``id``, ``values``, and ``metadata`` keys.
        """
        if not records:
            return
        self._ensure_index()
        self._index.upsert(vectors=records, namespace=namespace)  # type: ignore[union-attr]

    def upsert_one(
        self,
        *,
        vector_id: str,
        values: list[float],
        metadata: dict,
        namespace: str = "",
    ) -> None:
        """Convenience wrapper for upserting a single vector."""
        self.upsert_records(
            [VectorRecord(id=vector_id, values=values, metadata=metadata)],
            namespace=namespace,
        )

    def query(
        self,
        *,
        vector: list[float],
        top_k: int = 10,
        namespace: str = "",
        filter: dict | None = None,
    ) -> list[dict]:
        """Return the *top_k* nearest neighbours of *vector*."""
        self._ensure_index()
        result = self._index.query(  # type: ignore[union-attr]
            vector=vector,
            top_k=top_k,
            namespace=namespace,
            filter=filter,
            include_metadata=True,
        )
        return [
            {"id": m.id, "score": m.score, "metadata": m.metadata or {}}
            for m in result.matches
        ]

    def delete(self, *, vector_ids: list[str], namespace: str = "") -> None:
        """Delete vectors by ID."""
        self._ensure_index()
        self._index.delete(ids=vector_ids, namespace=namespace)  # type: ignore[union-attr]

    def close(self) -> None:
        return
