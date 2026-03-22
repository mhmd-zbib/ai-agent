"""
Stage 4 — Store Service.

Receives an EmbedEvent, builds a rich Pinecone metadata record, upserts
the vector, records the chunk in Postgres, and marks the document
``completed`` when all chunks have been stored.

Metadata attached to every Pinecone vector
------------------------------------------
document_id   — filter by document for delete / refresh
upload_id     — traceability back to the upload flow
user_id       — tenant identifier (also expressed as namespace)
file_name     — shown in search result snippets
content_type  — filter by file type (pdf, docx, …)
chunk_id      — exact chunk reference for re-fetch
chunk_index   — ordering; useful for reassembling context windows
total_chunks  — allows callers to know how complete the document is
source_page   — PDF page citation (omitted when not available)
chunk_text    — stored inline so retrieval results are self-contained;
                avoids a Postgres round-trip on every RAG lookup.

Namespace = user_id
    Every vector lives in a namespace keyed to its owner, giving cheap
    tenant isolation without a metadata filter on every query.
"""

from app.shared.protocols import IVectorClient
from app.shared.protocols import VectorRecord
from app.modules.pipeline.repositories.document_status_repository import (
    DocumentStatus,
    IDocumentStatusRepository,
)
from app.modules.pipeline.schemas.events import EmbedEvent, StoredEvent
from app.shared.logging import get_logger

logger = get_logger(__name__)

# Pinecone's hard limit is 40 KB per metadata object.
# 512-token chunks are ~2 000–4 000 chars — storing the full text is safe.
# We apply a generous cap only as a defensive measure.
_MAX_CHUNK_TEXT_CHARS = 10_000


def _build_metadata(event: EmbedEvent) -> dict:
    """
    Construct the Pinecone metadata dict from an :class:`EmbedEvent`.

    All fields are scalar (string, int, float) so they can be used as
    Pinecone filter operands.  The dict is intentionally flat — nested
    objects are not supported in Pinecone metadata filters.
    """
    meta: dict = {
        "document_id": event.document_id,
        "upload_id": event.upload_id,
        "file_name": event.file_name,
        "chunk_id": event.chunk_id,
        "chunk_index": event.chunk_index,
        "total_chunks": event.total_chunks,
        "chunk_text": event.chunk_text[:_MAX_CHUNK_TEXT_CHARS],
    }

    if event.user_id:
        meta["user_id"] = event.user_id

    if event.content_type:
        meta["content_type"] = event.content_type

    if event.source_page is not None:
        meta["source_page"] = event.source_page

    return meta


class StoreService:
    def __init__(
        self,
        *,
        vector_client: IVectorClient,
        status_repository: IDocumentStatusRepository,
    ) -> None:
        self._vector_client = vector_client
        self._status_repo = status_repository

    def process(self, event: EmbedEvent) -> StoredEvent:
        """
        Store a single chunk vector in Pinecone and track it in Postgres.

        Flow
        ----
        1. chunk_index == 0  → Postgres status ``storing``
        2. Build metadata record
        3. Upsert into Pinecone under namespace = user_id
        4. Record chunk in Postgres document_chunks
        5. Count stored chunks; if == total_chunks → status ``completed``
        6. Return :class:`StoredEvent`
        """
        document_id = event.document_id
        vector_id = event.chunk_id  # deterministic: {document_id}_chunk_{n:06d}
        namespace = event.user_id or ""

        # Conditional update: only the first chunk to arrive sets the status.
        # Subsequent chunks are a no-op because status is no longer 'embedding'.
        self._status_repo.update_status_conditional(
            document_id=document_id,
            new_status=DocumentStatus.STORING,
            from_status=DocumentStatus.EMBEDDING,
        )

        try:
            record = VectorRecord(
                id=vector_id,
                values=event.vector,
                metadata=_build_metadata(event),
            )

            self._vector_client.upsert_records([record], namespace=namespace)

            logger.info(
                "Chunk stored in Pinecone",
                extra={
                    "document_id": document_id,
                    "chunk_id": event.chunk_id,
                    "chunk_index": event.chunk_index,
                    "total_chunks": event.total_chunks,
                    "namespace": namespace,
                    "vector_id": vector_id,
                },
            )

            # Record in Postgres
            self._status_repo.record_chunk_stored(
                document_id=document_id,
                chunk_id=event.chunk_id,
                chunk_index=event.chunk_index,
                source_page=event.source_page,
                vector_id=vector_id,
            )

            stored_count = self._status_repo.count_stored_chunks(
                document_id=document_id
            )
            is_last = stored_count >= event.total_chunks

            if is_last:
                self._status_repo.update_status(
                    document_id=document_id,
                    status=DocumentStatus.COMPLETED,
                )
                logger.info(
                    "Document ingestion completed",
                    extra={
                        "document_id": document_id,
                        "upload_id": event.upload_id,
                        "file_name": event.file_name,
                        "total_chunks": event.total_chunks,
                        "namespace": namespace,
                    },
                )

            return StoredEvent(
                document_id=document_id,
                chunk_id=event.chunk_id,
                chunk_index=event.chunk_index,
                vector_id=vector_id,
                is_last_chunk=is_last,
            )

        except Exception as exc:
            self._status_repo.update_status_failed(
                document_id=document_id,
                error_message=str(exc),
            )
            raise
