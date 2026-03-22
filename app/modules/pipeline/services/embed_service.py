"""
Stage 3 — Embed Service.

Depends on the IEmbeddingClient port so the embedding provider can be swapped
via config without touching this service. The concrete adapter (OpenAI, Ollama,
Azure, etc.) is injected by the consumer / composition root.
"""

from app.shared.protocols import IEmbeddingClient
from app.modules.pipeline.repositories.document_status_repository import (
    DocumentStatus,
    IDocumentStatusRepository,
)
from app.modules.pipeline.schemas.events import ChunkEvent, EmbedEvent
from app.shared.logging import get_logger

logger = get_logger(__name__)


class EmbedService:
    def __init__(
        self,
        *,
        embedding_client: IEmbeddingClient,
        status_repository: IDocumentStatusRepository,
    ) -> None:
        self._client = embedding_client
        self._status_repo = status_repository

    def process(self, event: ChunkEvent) -> EmbedEvent:
        """
        Embed a single chunk and return an EmbedEvent.

        Flow
        ----
        1. Atomically transition Postgres status chunked → embedding
           (no-op if another chunk already set it — fixes race condition)
        2. Call the embedding client
        3. Return EmbedEvent with vector + full metadata
        """
        document_id = event.document_id

        # Conditional update: only the first chunk to arrive sets the status.
        # Subsequent chunks are a no-op because status is no longer 'chunked'.
        self._status_repo.update_status_conditional(
            document_id=document_id,
            new_status=DocumentStatus.EMBEDDING,
            from_status=DocumentStatus.CHUNKED,
        )

        try:
            vector = self._client.embed(event.chunk_text)

            logger.info(
                "Chunk embedded",
                extra={
                    "document_id": document_id,
                    "chunk_id": event.chunk_id,
                    "chunk_index": event.chunk_index,
                    "total_chunks": event.total_chunks,
                    "source_page": event.source_page,
                    "tenant_id": event.user_id,
                    "file_type": event.content_type,
                    "vector_dim": len(vector),
                },
            )

            return EmbedEvent(
                document_id=document_id,
                upload_id=event.upload_id,
                user_id=event.user_id,
                file_name=event.file_name,
                content_type=event.content_type,
                chunk_id=event.chunk_id,
                chunk_index=event.chunk_index,
                chunk_text=event.chunk_text,
                source_page=event.source_page,
                total_chunks=event.total_chunks,
                vector=vector,
            )

        except Exception as exc:
            self._status_repo.update_status_failed(
                document_id=document_id,
                error_message=str(exc),
            )
            raise
