"""Document upload service factory."""

import os

from redis import Redis

from api.documents.repository import MinIOBucketRepository, UploadSessionRepository
from api.documents.service import DocumentUploadService
from common.core.config import Settings
from common.infra.messaging.rabbitmq import RabbitMQPublisher
from common.infra.storage.minio import MinioStorageClient


def create_document_upload_service(
    settings: Settings,
    redis_client: Redis,
) -> DocumentUploadService:
    minio_client = MinioStorageClient(
        endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
        access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        bucket_name=os.getenv("MINIO_BUCKET_NAME", "documents"),
        secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
    )
    rabbitmq_publisher = RabbitMQPublisher(
        amqp_url=os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/%2F"),
        exchange=os.getenv("RABBITMQ_DOCUMENT_EXCHANGE", "documents.exchange"),
        routing_key=os.getenv("RABBITMQ_DOCUMENT_ROUTING_KEY", "documents.uploaded"),
        exchange_type="topic",
    )
    return DocumentUploadService(
        session_repo=UploadSessionRepository(redis_client),
        bucket_repo=MinIOBucketRepository(minio_client),
        rabbitmq_publisher=rabbitmq_publisher,
    )
