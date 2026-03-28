"""app.documents.repository — Upload session and bucket storage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

from api.documents.schemas import ChunkingStrategy, UploadSession
from common.core.log_config import get_logger
from redis import Redis

logger = get_logger(__name__)


class UploadSessionRepository:
    """Manages upload sessions (in-memory cache via Redis)."""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self._prefix = "upload_session:"
        self._session_ttl_seconds = 3600  # 1 hour

    def create_session(
        self,
        document_name: str,
        content_type: str,
        total_size_bytes: int,
        chunking_strategy: ChunkingStrategy,
        user_id: str,
        bucket_key: str,
    ) -> UploadSession:
        """Create a new upload session."""
        session_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self._session_ttl_seconds)

        session = UploadSession(
            upload_session_id=session_id,
            document_name=document_name,
            content_type=content_type,
            total_size_bytes=total_size_bytes,
            chunking_strategy=chunking_strategy,
            bucket_key=bucket_key,
            user_id=user_id,
            created_at=now,
            expires_at=expires_at,
            status="active",
        )

        # Store in Redis as JSON
        key = f"{self._prefix}{session_id}"
        self.redis.setex(
            key,
            self._session_ttl_seconds,
            session.model_dump_json(),
        )

        logger.info(
            "Created upload session",
            extra={"session_id": session_id, "user_id": user_id},
        )
        return session

    def get_session(self, session_id: str) -> Optional[UploadSession]:
        """Retrieve an upload session by ID."""
        key = f"{self._prefix}{session_id}"
        data = self.redis.get(key)

        if not data:
            logger.warning(
                "Upload session not found",
                extra={"session_id": session_id},
            )
            return None

        return UploadSession.model_validate_json(data)

    def record_chunk_received(self, session_id: str, chunk_number: int) -> bool:
        """Record that a chunk was received."""
        session = self.get_session(session_id)
        if not session:
            return False

        session.chunks_received.add(chunk_number)
        key = f"{self._prefix}{session_id}"
        self.redis.setex(
            key,
            self._session_ttl_seconds,
            session.model_dump_json(),
        )

        logger.debug(
            "Recorded chunk received",
            extra={
                "session_id": session_id,
                "chunk_number": chunk_number,
                "total_received": len(session.chunks_received),
            },
        )
        return True

    def mark_complete(self, session_id: str) -> Optional[UploadSession]:
        """Mark an upload session as complete."""
        session = self.get_session(session_id)
        if not session:
            return None

        session.status = "complete"
        key = f"{self._prefix}{session_id}"
        self.redis.setex(
            key,
            self._session_ttl_seconds,
            session.model_dump_json(),
        )

        logger.info(
            "Marked upload session complete",
            extra={"session_id": session_id},
        )
        return session

    def mark_failed(self, session_id: str, reason: str = "") -> Optional[UploadSession]:
        """Mark an upload session as failed."""
        session = self.get_session(session_id)
        if not session:
            return None

        session.status = "failed"
        key = f"{self._prefix}{session_id}"
        self.redis.setex(
            key,
            300,  # Keep for 5 minutes for debugging
            session.model_dump_json(),
        )

        logger.warning(
            "Upload session failed",
            extra={"session_id": session_id, "reason": reason},
        )
        return session


class MinIOBucketRepository:
    """Adapter around infra MinioStorageClient for upload flow operations."""

    def __init__(self, minio_client):
        self.minio = minio_client

    def get_presigned_upload_url(
        self, object_name: str, expires_in_seconds: int = 3600
    ) -> str:
        try:
            url = self.minio.presigned_put_url(
                object_key=object_name,
                expires=timedelta(seconds=expires_in_seconds),
            )
            logger.debug(
                "Generated presigned URL",
                extra={"object": object_name, "expires_in_seconds": expires_in_seconds},
            )
            return url
        except Exception as e:
            logger.error(
                "Failed to generate presigned URL",
                extra={"object": object_name, "error": str(e)},
            )
            raise

    def get_document(self, object_name: str) -> bytes:
        try:
            data = self.minio.download_bytes(object_key=object_name)
            logger.debug(
                "Retrieved document from bucket",
                extra={"object": object_name},
            )
            return data
        except Exception as e:
            logger.error(
                "Failed to retrieve document",
                extra={"object": object_name, "error": str(e)},
            )
            raise

    def upload_document(self, object_name: str, data: bytes) -> bool:
        try:
            self.minio.upload_bytes(object_key=object_name, payload=data)
            logger.info(
                "Uploaded document to bucket",
                extra={"object": object_name},
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to upload document",
                extra={"object": object_name, "error": str(e)},
            )
            return False

