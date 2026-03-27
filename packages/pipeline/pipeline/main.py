"""Pipeline FastAPI application — composition root.

Exposes:
  POST /v1/uploads                       — initiate a multipart upload
  POST /v1/uploads/{upload_id}/complete  — complete a multipart upload
  GET  /v1/jobs                          — list pipeline jobs (paginated)
  GET  /v1/jobs/{job_id}                 — get a single job by ID
  GET  /health                           — liveness probe
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.exceptions import ConfigurationError, register_exception_handlers
from shared.logging import configure_logging, get_logger
from shared.messaging.rabbitmq import RabbitMQPublisher
from shared.storage.minio import MinioStorageClient

from pipeline.health.router import router as health_router
from pipeline.jobs.repository import JobRepository
from pipeline.jobs.router import router as jobs_router
from pipeline.jobs.service import JobService
from pipeline.upload.repository import MinioDocumentStorageRepository
from pipeline.upload.router import router as upload_router
from pipeline.upload.service import UploadService

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Required environment variable '{name}' is not set.")
    return value


def _optional_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------


def _build_upload_service() -> UploadService:
    """Wire UploadService from environment variables."""
    minio_endpoint = _require_env("MINIO_ENDPOINT")
    minio_access_key = _require_env("MINIO_ACCESS_KEY")
    minio_secret_key = _require_env("MINIO_SECRET_KEY")
    minio_bucket = _optional_env("MINIO_BUCKET", "documents")
    minio_secure = _optional_env("MINIO_SECURE", "false").lower() == "true"

    amqp_url = _require_env("AMQP_URL")
    exchange = _optional_env("AMQP_EXCHANGE", "documents.fanout")
    routing_key = _optional_env("AMQP_ROUTING_KEY", "")
    exchange_type = _optional_env("AMQP_EXCHANGE_TYPE", "fanout")

    default_chunk_bytes_raw = _optional_env("DEFAULT_CHUNK_SIZE_BYTES", str(10 * 1024 * 1024))
    try:
        default_chunk_bytes = int(default_chunk_bytes_raw)
    except ValueError:
        raise ConfigurationError(
            f"DEFAULT_CHUNK_SIZE_BYTES must be an integer, got '{default_chunk_bytes_raw}'."
        )

    minio_client = MinioStorageClient(
        endpoint=minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        bucket_name=minio_bucket,
        secure=minio_secure,
    )
    storage = MinioDocumentStorageRepository(minio_client)

    publisher = RabbitMQPublisher(
        amqp_url=amqp_url,
        exchange=exchange,
        routing_key=routing_key,
        exchange_type=exchange_type,
    )

    return UploadService(
        bucket_name=minio_bucket,
        default_chunk_size_bytes=default_chunk_bytes,
        storage=storage,
        publisher=publisher,
        document_record_repository=None,
    )


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log_level = _optional_env("LOG_LEVEL", "INFO")
    configure_logging(log_level)

    logger.info("Pipeline service starting up")

    job_repository = JobRepository()
    job_service = JobService(job_repository)
    upload_service = _build_upload_service()

    app.state.job_repository = job_repository
    app.state.job_service = job_service
    app.state.upload_service = upload_service

    logger.info("Pipeline service ready")
    try:
        yield
    finally:
        logger.info("Pipeline service shutting down")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pipeline API",
        description=(
            "Document upload and pipeline job tracking service. "
            "Clients upload documents in chunks via presigned MinIO URLs; "
            "the service publishes events to RabbitMQ to trigger downstream processing."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(upload_router, prefix="/v1")
    app.include_router(jobs_router, prefix="/v1")
    app.include_router(health_router)

    register_exception_handlers(app)

    return app


app = create_app()

__all__ = ["app", "create_app"]
