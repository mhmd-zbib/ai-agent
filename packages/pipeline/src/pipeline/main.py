"""Pipeline worker entry point.

Connects to RabbitMQ, consumes DocumentUploadedEvent messages from the
documents.fanout exchange, and runs the 4-stage ingestion pipeline.
"""

from __future__ import annotations

import asyncio
import os
import signal
import threading

from common.core.log_config import configure_logging, get_logger
from common.infra.messaging.rabbitmq import RabbitMQConsumer

logger = get_logger(__name__)


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable '{name}' is not set.")
    return value


def _optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _handle_message(payload: dict) -> None:
    """Process a single DocumentUploadedEvent payload."""
    from pipeline.ingestion.service import ingest_document

    document_key = payload.get("document_key", "")
    course_id = payload.get("course_id", "")
    source_type = payload.get("source_type", "textbook")

    if not document_key or not course_id:
        logger.warning(
            "Invalid message payload",
            extra={"payload_keys": list(payload.keys())},
        )
        return

    logger.info(
        "Processing document",
        extra={"document_key": document_key, "course_id": course_id},
    )

    try:
        ingest_document(
            document_key=document_key,
            course_id=course_id,
            source_type=source_type,
        )
        logger.info("Document ingestion complete", extra={"document_key": document_key})
    except Exception as exc:
        logger.error(
            "Document ingestion failed",
            extra={"document_key": document_key, "error": str(exc)},
        )
        raise


def main() -> None:
    """Start the pipeline worker."""
    log_level = _optional_env("LOG_LEVEL", "INFO")
    configure_logging(log_level)

    amqp_url = _require_env("AMQP_URL")
    queue_name = _optional_env("PIPELINE_QUEUE", "pipeline.ingest")
    dlq_name = _optional_env("PIPELINE_DLQ", "pipeline.ingest.dlq")

    logger.info(
        "Pipeline worker starting",
        extra={"queue": queue_name, "dlq": dlq_name},
    )

    consumer = RabbitMQConsumer(
        amqp_url=amqp_url,
        queue_name=queue_name,
        dlq_name=dlq_name,
        prefetch_count=1,
    )

    # Graceful shutdown on SIGTERM/SIGINT
    stop_event = threading.Event()

    def _shutdown(signum: int, frame: object) -> None:
        logger.info("Shutdown signal received", extra={"signal": signum})
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Pipeline worker ready, consuming messages")
    consumer.consume_forever(_handle_message)


if __name__ == "__main__":
    main()
