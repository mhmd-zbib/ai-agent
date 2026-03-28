"""app.documents.service — Document upload orchestration."""

from __future__ import annotations

from uuid import uuid4

from api.documents.repository import MinIOBucketRepository, UploadSessionRepository
from api.documents.schemas import (
    BucketInfoRequest,
    BucketInfoResponse,
    ChunkUploadNotification,
    ChunkUploadResponse,
    DocumentUploadCompleteRequest,
    DocumentUploadCompleteResponse,
)
from common.core.log_config import get_logger
from common.infra.messaging.rabbitmq import RabbitMQPublisher

logger = get_logger(__name__)


class DocumentUploadService:
    """Orchestrates document uploads: credentials → chunks → ingestion."""

    def __init__(
        self,
        session_repo: UploadSessionRepository,
        bucket_repo: MinIOBucketRepository,
        rabbitmq_publisher: RabbitMQPublisher,
    ):
        self.session_repo = session_repo
        self.bucket_repo = bucket_repo
        self.rabbitmq = rabbitmq_publisher

    def initiate_upload(self, request: BucketInfoRequest, user_id: str) -> BucketInfoResponse:
        """
        Step 1: Client initiates upload.

        Returns bucket credentials and metadata needed for chunked upload.
        """
        # Generate upload session and bucket key
        session_id = str(uuid4())
        bucket_key = f"uploads/{user_id}/{session_id}/{request.document_name}"

        # Calculate chunk size and max chunks
        chunk_size_bytes = 5 * 1024 * 1024  # 5MB chunks
        max_chunks = (request.total_size_bytes // chunk_size_bytes) + 1

        # Create session in Redis
        session = self.session_repo.create_session(
            document_name=request.document_name,
            content_type=request.content_type,
            total_size_bytes=request.total_size_bytes,
            chunking_strategy=request.chunking_strategy,
            user_id=user_id,
            bucket_key=bucket_key,
        )

        # Get presigned URL for direct bucket uploads
        presigned_url = self.bucket_repo.get_presigned_upload_url(
            bucket_key, expires_in_seconds=3600
        )

        logger.info(
            "Upload initiated",
            extra={
                "session_id": session_id,
                "user_id": user_id,
                "document_name": request.document_name,
                "max_chunks": max_chunks,
            },
        )

        return BucketInfoResponse(
            upload_session_id=session_id,
            bucket_name="documents",
            bucket_region=None,
            presigned_url=presigned_url,
            chunk_size_bytes=chunk_size_bytes,
            max_chunks=max_chunks,
            expires_in_seconds=3600,
            metadata={
                "content_type": request.content_type,
                "chunking_strategy": request.chunking_strategy,
            },
        )

    def notify_chunk_received(
        self, notification: ChunkUploadNotification
    ) -> ChunkUploadResponse:
        """
        Step 2: Client notifies backend of completed chunk.

        Backend records chunk receipt and stores metadata.
        """
        session = self.session_repo.get_session(notification.upload_session_id)
        if not session:
            logger.warning(
                "Chunk notification for unknown session",
                extra={"session_id": notification.upload_session_id},
            )
            return ChunkUploadResponse(
                upload_session_id=notification.upload_session_id,
                chunk_number=notification.chunk_number,
                status="error",
                message="Session not found",
            )

        # Record chunk receipt
        self.session_repo.record_chunk_received(
            notification.upload_session_id, notification.chunk_number
        )

        logger.debug(
            "Chunk notification received",
            extra={
                "session_id": notification.upload_session_id,
                "chunk_number": notification.chunk_number,
                "chunk_hash": notification.chunk_hash,
                "chunks_received": len(session.chunks_received),
            },
        )

        return ChunkUploadResponse(
            upload_session_id=notification.upload_session_id,
            chunk_number=notification.chunk_number,
            status="stored",
            message=f"Chunk {notification.chunk_number} received and stored",
        )

    def complete_upload(
        self, request: DocumentUploadCompleteRequest
    ) -> DocumentUploadCompleteResponse:
        """
        Step 3: Client signals upload completion.

        Backend:
        1. Validates all chunks received
        2. Updates session status
        3. Publishes DocumentUploadedEvent to RabbitMQ
        4. Pipeline consumer fetches document and starts ingestion
        """
        session = self.session_repo.get_session(request.upload_session_id)
        if not session:
            logger.error(
                "Upload completion for unknown session",
                extra={"session_id": request.upload_session_id},
            )
            raise ValueError(f"Session {request.upload_session_id} not found")

        # Validate chunk count
        if len(session.chunks_received) != request.total_chunks:
            missing = set(range(1, request.total_chunks + 1)) - session.chunks_received
            logger.warning(
                "Upload complete but missing chunks",
                extra={
                    "session_id": request.upload_session_id,
                    "expected": request.total_chunks,
                    "received": len(session.chunks_received),
                    "missing": sorted(missing),
                },
            )
            self.session_repo.mark_failed(
                request.upload_session_id,
                f"Missing chunks: {missing}",
            )
            raise ValueError(f"Missing chunks: {sorted(missing)}")

        # Mark session complete
        self.session_repo.mark_complete(request.upload_session_id)

        # Publish event to RabbitMQ for pipeline
        job_id = str(uuid4())
        event_payload = {
            "event_type": "DocumentUploadedEvent",
            "job_id": job_id,
            "upload_session_id": request.upload_session_id,
            "document_key": session.bucket_key,
            "document_name": session.document_name,
            "content_type": session.content_type,
            "total_size_bytes": session.total_size_bytes,
            "chunking_strategy": session.chunking_strategy,
            "user_id": session.user_id,
            "course_id": request.course_id,
            "file_hash": request.file_hash,
            "metadata": request.document_metadata,
        }

        try:
            self.rabbitmq.publish_json(event_payload)
            logger.info(
                "Published DocumentUploadedEvent",
                extra={
                    "session_id": request.upload_session_id,
                    "job_id": job_id,
                    "document_key": session.bucket_key,
                },
            )
        except Exception as e:
            logger.error(
                "Failed to publish DocumentUploadedEvent",
                extra={
                    "session_id": request.upload_session_id,
                    "error": str(e),
                },
            )
            self.session_repo.mark_failed(
                request.upload_session_id, f"Failed to publish event: {e}"
            )
            raise

        return DocumentUploadCompleteResponse(
            document_key=session.bucket_key,
            ingestion_job_id=job_id,
            status="queued",
            message=f"Upload complete. Ingestion job {job_id} queued for processing.",
        )
