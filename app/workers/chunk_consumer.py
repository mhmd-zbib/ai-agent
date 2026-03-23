"""
Stage 2 — Chunk Consumer.

Listens on ``documents.chunk.queue``. For each ParsedEvent:
  - Downloads parsed text (and pages JSON for PDFs) from MinIO
  - Applies the sliding-window chunker
  - Updates Postgres status parsed → chunking → chunked + stores total_chunks
  - Publishes one ChunkEvent per chunk to ``documents.embed.queue``
  - On any failure: nacks to ``documents.chunk.dlq`` + marks status failed
"""

from app.infrastructure.database.postgres import create_postgres_engine
from app.infrastructure.messaging.rabbitmq import (
    RabbitMQConsumer,
    publish_batch_to_queue,
)
from app.infrastructure.storage.minio import MinioStorageClient
from app.modules.pipeline.repositories.document_status_repository import (
    DocumentStatusRepository,
)
from app.modules.pipeline.schemas.events import ParsedEvent
from app.modules.pipeline.services.chunk_service import ChunkService
from app.shared.config import get_settings
from app.shared.logging import configure_logging, get_logger

logger = get_logger(__name__)


def _make_handler(chunk_service: ChunkService, amqp_url: str, embed_queue: str):
    def handle(payload: dict) -> None:
        event = ParsedEvent.model_validate(payload)
        logger.info(
            "chunk_consumer received document.parsed",
            extra={
                "document_id": event.document_id,
                "upload_id": event.upload_id,
                "parsed_text_key": event.parsed_text_key,
            },
        )

        chunk_events = chunk_service.process(event)

        publish_batch_to_queue(
            amqp_url,
            embed_queue,
            [ce.model_dump(mode="json") for ce in chunk_events],
        )

        logger.info(
            "ChunkEvents published to embed.queue",
            extra={
                "document_id": event.document_id,
                "chunk_count": len(chunk_events),
            },
        )

    return handle


def consume_forever() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = create_postgres_engine(
        database_url=settings.database_url or "",
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout_seconds=settings.postgres_pool_timeout_seconds,
    )

    status_repo = DocumentStatusRepository(engine)
    status_repo.ensure_schema()

    storage = MinioStorageClient(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket_name=settings.minio_bucket_name,
        secure=settings.minio_secure,
    )

    chunk_service = ChunkService(
        storage=storage,
        status_repository=status_repo,
        window_tokens=settings.chunk_window_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
        encoding=settings.chunk_encoding,
    )

    consumer = RabbitMQConsumer(
        amqp_url=settings.rabbitmq_url,
        queue_name=settings.rabbitmq_chunk_queue,
        dlq_name=settings.rabbitmq_chunk_dlq,
    )

    logger.info(
        "Starting chunk consumer",
        extra={
            "queue": settings.rabbitmq_chunk_queue,
            "dlq": settings.rabbitmq_chunk_dlq,
            "embed_queue": settings.rabbitmq_embed_queue,
            "window_tokens": settings.chunk_window_tokens,
            "overlap_tokens": settings.chunk_overlap_tokens,
        },
    )

    handler = _make_handler(
        chunk_service,
        settings.rabbitmq_url,
        settings.rabbitmq_embed_queue,
    )
    consumer.consume_forever(handler)


if __name__ == "__main__":
    consume_forever()
