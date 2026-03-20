import json
from collections.abc import Callable
from typing import Any

from app.shared.config import get_settings
from app.shared.logging import configure_logging, get_logger

logger = get_logger(__name__)


def _log_uploaded_event(payload: dict[str, object]) -> None:
    logger.info(
        "document.uploaded consumed",
        extra={
            "event_id": payload.get("event_id"),
            "upload_id": payload.get("upload_id"),
            "bucket": payload.get("bucket"),
            "chunk_count": payload.get("chunk_count"),
            "total_size_bytes": payload.get("total_size_bytes"),
        },
    )


def _build_callback(
    handler: Callable[[dict[str, object]], None],
) -> Callable[[Any, Any, Any, bytes], None]:
    def _callback(
        channel: Any,
        method: Any,
        properties: Any,  # noqa: ARG001
        body: bytes,
    ) -> None:
        try:
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object payload")
            handler(payload)
            channel.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            logger.exception("Failed to process uploaded document event")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    return _callback


def consume_forever() -> None:
    import pika

    settings = get_settings()
    configure_logging(settings.log_level)

    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = connection.channel()

    channel.exchange_declare(
        exchange=settings.rabbitmq_document_exchange,
        exchange_type="topic",
        durable=True,
    )
    channel.queue_declare(queue=settings.rabbitmq_document_queue, durable=True)
    channel.queue_bind(
        exchange=settings.rabbitmq_document_exchange,
        queue=settings.rabbitmq_document_queue,
        routing_key=settings.rabbitmq_document_routing_key,
    )
    channel.basic_qos(prefetch_count=1)

    logger.info(
        "Starting document upload consumer",
        extra={
            "queue": settings.rabbitmq_document_queue,
            "exchange": settings.rabbitmq_document_exchange,
            "routing_key": settings.rabbitmq_document_routing_key,
        },
    )

    callback = _build_callback(_log_uploaded_event)
    channel.basic_consume(queue=settings.rabbitmq_document_queue, on_message_callback=callback)
    channel.start_consuming()


if __name__ == "__main__":
    consume_forever()
