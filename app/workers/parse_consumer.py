"""
Stage 1 — Parse Consumer.

Listens on ``documents.parse.queue`` (bound to the ``documents.fanout``
exchange). For each document.uploaded event:
  - Downloads all upload chunks from MinIO and reassembles the file
  - Routes to the correct parser (PDF / DOCX / text)
  - Updates Postgres status uploaded → parsing → parsed
  - Publishes a ParsedEvent to ``documents.chunk.queue``
  - On any failure: nacks to ``documents.parse.dlq`` + marks status failed
"""

from app.infrastructure.database.postgres import create_postgres_engine
from app.infrastructure.messaging.rabbitmq import RabbitMQConsumer, publish_to_queue
from app.infrastructure.storage.minio import MinioStorageClient
from app.modules.documents.schemas.events import DocumentUploadedEvent
from app.modules.pipeline.repositories.document_status_repository import (
    DocumentStatusRepository,
)
from app.modules.pipeline.services.parse_service import ParseService
from app.shared.config import get_settings
from app.shared.logging import configure_logging, get_logger

logger = get_logger(__name__)


def _make_handler(parse_service: ParseService, amqp_url: str, chunk_queue: str):
    def handle(payload: dict) -> None:
        event = DocumentUploadedEvent.model_validate(payload)
        logger.info(
            "parse_consumer received document.uploaded",
            extra={
                "document_id": event.document_id,
                "upload_id": event.upload_id,
                "file_name": event.file_name,
            },
        )

        parsed_event = parse_service.process(event)

        publish_to_queue(
            amqp_url,
            chunk_queue,
            parsed_event.model_dump(mode="json"),
        )
        logger.info(
            "ParsedEvent published to chunk.queue",
            extra={
                "document_id": parsed_event.document_id,
                "upload_id": parsed_event.upload_id,
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

    parse_service = ParseService(storage=storage, status_repository=status_repo)

    consumer = RabbitMQConsumer(
        amqp_url=settings.rabbitmq_url,
        queue_name=settings.rabbitmq_parse_queue,
        dlq_name=settings.rabbitmq_parse_dlq,
    )

    logger.info(
        "Starting parse consumer",
        extra={
            "queue": settings.rabbitmq_parse_queue,
            "dlq": settings.rabbitmq_parse_dlq,
            "chunk_queue": settings.rabbitmq_chunk_queue,
        },
    )

    handler = _make_handler(
        parse_service,
        settings.rabbitmq_url,
        settings.rabbitmq_chunk_queue,
    )
    consumer.consume_forever(handler)


if __name__ == "__main__":
    consume_forever()
