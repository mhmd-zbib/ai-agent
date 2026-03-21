"""
Stage 4 — Store Consumer.

Listens on ``documents.store.queue``. For each EmbedEvent:
  - Upserts the vector into Pinecone with rich metadata
  - Records the chunk in Postgres document_chunks
  - When all chunks for a document are stored, marks status ``completed``
  - On any failure: nacks to ``documents.store.dlq`` + marks status failed
"""

from app.infrastructure.database.postgres import create_postgres_engine
from app.infrastructure.messaging.rabbitmq import RabbitMQConsumer
from app.infrastructure.vector.pinecone import PineconeVectorClient
from app.modules.pipeline.repositories.document_status_repository import (
    DocumentStatusRepository,
)
from app.modules.pipeline.schemas.events import EmbedEvent
from app.modules.pipeline.services.store_service import StoreService
from app.shared.config import get_settings
from app.shared.logging import configure_logging, get_logger

logger = get_logger(__name__)


def _make_handler(store_service: StoreService):
    def handle(payload: dict) -> None:
        event = EmbedEvent.model_validate(payload)
        logger.debug(
            "store_consumer received document.embedded",
            extra={
                "document_id": event.document_id,
                "chunk_id": event.chunk_id,
                "chunk_index": event.chunk_index,
                "total_chunks": event.total_chunks,
            },
        )

        stored = store_service.process(event)

        if stored.is_last_chunk:
            logger.info(
                "All chunks stored — document ingestion complete",
                extra={
                    "document_id": stored.document_id,
                    "total_chunks": event.total_chunks,
                },
            )

    return handle


def consume_forever() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    if not settings.pinecone_api_key:
        raise RuntimeError("PINECONE_API_KEY is required for the store consumer")

    engine = create_postgres_engine(
        database_url=settings.database_url or "",
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout_seconds=settings.postgres_pool_timeout_seconds,
    )

    status_repo = DocumentStatusRepository(engine)
    status_repo.ensure_schema()

    pinecone_client = PineconeVectorClient(
        api_key=settings.pinecone_api_key,
        index_name=settings.pinecone_index_name,
        dimension=settings.embedding_dimension,
        cloud=settings.pinecone_cloud,
        region=settings.pinecone_region,
    )

    store_service = StoreService(
        pinecone_client=pinecone_client,
        status_repository=status_repo,
    )

    consumer = RabbitMQConsumer(
        amqp_url=settings.rabbitmq_url,
        queue_name=settings.rabbitmq_store_queue,
        dlq_name=settings.rabbitmq_store_dlq,
    )

    logger.info(
        "Starting store consumer",
        extra={
            "queue": settings.rabbitmq_store_queue,
            "dlq": settings.rabbitmq_store_dlq,
            "pinecone_index": settings.pinecone_index_name,
        },
    )

    handler = _make_handler(store_service)
    consumer.consume_forever(handler)


if __name__ == "__main__":
    consume_forever()
