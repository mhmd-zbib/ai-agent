"""
Stage 3 — Embed Consumer.

Listens on ``documents.embed.queue``. For each ChunkEvent:
  - Calls the configured embedding provider to obtain a dense vector
  - Atomically transitions Postgres status chunked → embedding (race-safe)
  - Publishes an EmbedEvent to ``documents.store.queue``
  - On any failure: nacks to ``documents.embed.dlq`` + marks status failed
"""

from app.infrastructure.database.postgres import create_postgres_engine
from app.infrastructure.embedding.openai import OpenAIEmbeddingClient
from app.infrastructure.messaging.rabbitmq import RabbitMQConsumer, publish_to_queue
from app.modules.pipeline.repositories.document_status_repository import (
    DocumentStatusRepository,
)
from app.modules.pipeline.schemas.events import ChunkEvent
from app.modules.pipeline.services.embed_service import EmbedService
from app.shared.config import get_settings
from app.shared.logging import configure_logging, get_logger

logger = get_logger(__name__)


def _make_handler(embed_service: EmbedService, amqp_url: str, store_queue: str):
    def handle(payload: dict) -> None:
        event = ChunkEvent.model_validate(payload)
        logger.debug(
            "embed_consumer received document.chunked",
            extra={
                "document_id": event.document_id,
                "chunk_id": event.chunk_id,
                "chunk_index": event.chunk_index,
                "total_chunks": event.total_chunks,
            },
        )

        embed_event = embed_service.process(event)

        publish_to_queue(
            amqp_url,
            store_queue,
            embed_event.model_dump(mode="json"),
        )

    return handle


def consume_forever() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    # Prefer EMBEDDING_API_KEY; fall back to OPENAI_API_KEY
    api_key = settings.embedding_api_key or settings.openai_api_key
    if not api_key or api_key == "not-needed":
        raise RuntimeError(
            "Set EMBEDDING_API_KEY (or OPENAI_API_KEY) to run the embed consumer"
        )

    engine = create_postgres_engine(
        database_url=settings.database_url or "",
        pool_size=settings.postgres_pool_size,
        max_overflow=settings.postgres_max_overflow,
        pool_timeout_seconds=settings.postgres_pool_timeout_seconds,
    )

    status_repo = DocumentStatusRepository(engine)
    status_repo.ensure_schema()

    embedding_client = OpenAIEmbeddingClient(
        api_key=api_key,
        model=settings.embedding_model,
        base_url=settings.embedding_base_url,
        dimensions=settings.embedding_dimension,
        max_retries=settings.embedding_max_retries,
    )

    embed_service = EmbedService(
        embedding_client=embedding_client,
        status_repository=status_repo,
    )

    consumer = RabbitMQConsumer(
        amqp_url=settings.rabbitmq_url,
        queue_name=settings.rabbitmq_embed_queue,
        dlq_name=settings.rabbitmq_embed_dlq,
    )

    logger.info(
        "Starting embed consumer",
        extra={
            "queue": settings.rabbitmq_embed_queue,
            "dlq": settings.rabbitmq_embed_dlq,
            "store_queue": settings.rabbitmq_store_queue,
            "embedding_model": embedding_client.model_name,
            "embedding_base_url": settings.embedding_base_url or "openai default",
        },
    )

    handler = _make_handler(
        embed_service,
        settings.rabbitmq_url,
        settings.rabbitmq_store_queue,
    )
    consumer.consume_forever(handler)


if __name__ == "__main__":
    consume_forever()
