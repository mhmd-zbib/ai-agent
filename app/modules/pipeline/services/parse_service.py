"""
Stage 1 — Parse Service.

Receives a DocumentUploadedEvent, downloads all upload chunks from MinIO,
reassembles the file, routes to the correct parser, cleans the text, and
returns a ParsedEvent ready to publish to chunk.queue.
"""

import json

from app.infrastructure.storage.minio import MinioStorageClient
from app.modules.documents.schemas.events import DocumentUploadedEvent
from app.modules.pipeline.parsers import get_parser
from app.modules.pipeline.repositories.document_status_repository import (
    DocumentStatus,
    IDocumentStatusRepository,
)
from app.modules.pipeline.schemas.events import ParsedEvent
from app.shared.logging import get_logger

logger = get_logger(__name__)


class ParseService:
    def __init__(
        self,
        *,
        storage: MinioStorageClient,
        status_repository: IDocumentStatusRepository,
    ) -> None:
        self._storage = storage
        self._status_repo = status_repository

    def process(self, event: DocumentUploadedEvent) -> ParsedEvent:
        """
        Parse the document described by *event*.

        Flow
        ----
        1. Update Postgres status → ``parsing``
        2. Download manifest from MinIO
        3. Download + concatenate all upload chunks
        4. Route to parser (PDF / DOCX / text)
        5. Update Postgres status → ``parsed``
        6. Return :class:`ParsedEvent`
        """
        document_id = event.document_id
        self._status_repo.update_status(
            document_id=document_id,
            status=DocumentStatus.PARSING,
        )

        try:
            # Download manifest
            manifest_bytes = self._storage.download_bytes(
                object_key=event.manifest_key,
            )
            manifest = json.loads(manifest_bytes)

            # Reassemble file from upload chunks
            chunk_keys: list[str] = manifest["chunk_keys"]
            file_bytes = b"".join(
                self._storage.download_bytes(object_key=key) for key in chunk_keys
            )

            logger.info(
                "Downloaded document for parsing",
                extra={
                    "document_id": document_id,
                    "upload_id": event.upload_id,
                    "file_name": event.file_name,
                    "size_bytes": len(file_bytes),
                },
            )

            # Parse
            parser = get_parser(event.content_type, event.file_name)
            parsed = parser.parse(file_bytes, file_name=event.file_name)

            # Persist extracted text back to MinIO as a .txt artifact
            parsed_text_key = f"{event.object_prefix}/parsed.txt"
            self._storage.upload_bytes(
                object_key=parsed_text_key,
                payload=parsed.text.encode("utf-8"),
                content_type="text/plain; charset=utf-8",
            )

            # Persist per-page texts for PDFs so the chunker can attribute source_page
            parsed_pages_key: str | None = None
            if parsed.pages is not None:
                parsed_pages_key = f"{event.object_prefix}/parsed_pages.json"
                self._storage.upload_bytes(
                    object_key=parsed_pages_key,
                    payload=json.dumps(parsed.pages).encode("utf-8"),
                    content_type="application/json",
                )

            logger.info(
                "Parsed text saved to MinIO",
                extra={
                    "document_id": document_id,
                    "parsed_text_key": parsed_text_key,
                    "parsed_pages_key": parsed_pages_key,
                    "text_length": len(parsed.text),
                },
            )

            self._status_repo.update_status(
                document_id=document_id,
                status=DocumentStatus.PARSED,
            )

            return ParsedEvent(
                document_id=document_id,
                upload_id=event.upload_id,
                user_id=event.user_id,
                file_name=event.file_name,
                content_type=event.content_type,
                bucket=event.bucket,
                object_prefix=event.object_prefix,
                parsed_text_key=parsed_text_key,
                parsed_pages_key=parsed_pages_key,
                total_pages=len(parsed.pages) if parsed.pages is not None else None,
            )

        except Exception as exc:
            self._status_repo.update_status_failed(
                document_id=document_id,
                error_message=str(exc),
            )
            raise
