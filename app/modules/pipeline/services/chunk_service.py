"""
Stage 2 — Chunk Service.

Receives a ParsedEvent, downloads the parsed text (and optional pages JSON for
PDFs) from MinIO, applies the sliding-window chunker, persists chunk_count to
Postgres, and returns a list of ChunkEvents — one per text chunk.
"""

import json

from app.shared.protocols import IFileStorage
from app.modules.pipeline.chunkers.sliding_window_chunker import SlidingWindowChunker
from app.modules.pipeline.repositories.document_status_repository import (
    DocumentStatus,
    IDocumentStatusRepository,
)
from app.modules.pipeline.schemas.events import ChunkEvent, ParsedEvent
from app.shared.logging import get_logger

logger = get_logger(__name__)


class ChunkService:
    def __init__(
        self,
        *,
        storage: IFileStorage,
        status_repository: IDocumentStatusRepository,
        window_tokens: int = 512,
        overlap_tokens: int = 50,
        encoding: str = "cl100k_base",
    ) -> None:
        self._storage = storage
        self._status_repo = status_repository
        self._chunker = SlidingWindowChunker(
            window_tokens=window_tokens,
            overlap_tokens=overlap_tokens,
            encoding=encoding,
        )

    def process(self, event: ParsedEvent) -> list[ChunkEvent]:
        """
        Chunk the parsed text from *event*.

        Flow
        ----
        1. Update Postgres status → ``chunking``
        2. Download parsed text from MinIO using parsed_text_key
        3. Download per-page texts from MinIO if parsed_pages_key is set (PDFs)
        4. Apply sliding-window chunker (with page attribution for PDFs)
        5. Persist total_chunks to Postgres documents table
        6. Update Postgres status → ``chunked``
        7. Return list of ChunkEvent (one per chunk)
        """
        document_id = event.document_id
        self._status_repo.update_status(
            document_id=document_id,
            status=DocumentStatus.CHUNKING,
        )

        try:
            # Download parsed text from MinIO — never from the event payload
            text_bytes = self._storage.download_bytes(object_key=event.parsed_text_key)
            text = text_bytes.decode("utf-8")

            # Download per-page texts for PDFs to enable source_page attribution
            pages: list[str] | None = None
            if event.parsed_pages_key:
                pages_bytes = self._storage.download_bytes(
                    object_key=event.parsed_pages_key
                )
                pages = json.loads(pages_bytes)

            chunks = self._chunker.chunk(
                document_id=document_id,
                text=text,
                pages=pages,
            )

            if not chunks:
                logger.warning(
                    "No chunks produced for document",
                    extra={"document_id": document_id, "upload_id": event.upload_id},
                )
                self._status_repo.update_status(
                    document_id=document_id,
                    status=DocumentStatus.COMPLETED,
                )
                return []

            total_chunks = len(chunks)

            # Persist chunk count as Postgres source of truth for completion detection
            self._status_repo.update_total_chunks(
                document_id=document_id,
                total_chunks=total_chunks,
            )
            self._status_repo.update_status(
                document_id=document_id,
                status=DocumentStatus.CHUNKED,
            )

            logger.info(
                "Document chunked",
                extra={
                    "document_id": document_id,
                    "upload_id": event.upload_id,
                    "total_chunks": total_chunks,
                    "parsed_text_key": event.parsed_text_key,
                },
            )

            return [
                ChunkEvent(
                    document_id=document_id,
                    upload_id=event.upload_id,
                    user_id=event.user_id,
                    file_name=event.file_name,
                    content_type=event.content_type,
                    chunk_id=chunk.chunk_id,
                    chunk_index=chunk.chunk_index,
                    chunk_text=chunk.chunk_text,
                    source_page=chunk.source_page,
                    total_chunks=total_chunks,
                )
                for chunk in chunks
            ]

        except Exception as exc:
            self._status_repo.update_status_failed(
                document_id=document_id,
                error_message=str(exc),
            )
            raise
