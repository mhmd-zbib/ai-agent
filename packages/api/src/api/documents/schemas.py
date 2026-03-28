"""app.documents.schemas — Upload and chunking data models."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class ChunkingStrategy(StrEnum):
    """Document chunking strategies."""

    FIXED = "fixed"  # Fixed-size chunks (e.g., 4KB)
    SEMANTIC = "semantic"  # Semantic-aware chunks
    PAGE_BASED = "page_based"  # Page-based chunking (for PDFs)


class BucketInfoRequest(BaseModel):
    """Request to get bucket upload credentials."""

    document_name: str = Field(..., min_length=1, max_length=500)
    content_type: str = Field(..., description="MIME type (e.g., application/pdf)")
    total_size_bytes: int = Field(..., gt=0, description="Total file size in bytes")
    chunking_strategy: ChunkingStrategy = Field(
        default=ChunkingStrategy.FIXED,
        description="How to chunk the document during ingestion",
    )


class BucketInfoResponse(BaseModel):
    """Response with bucket upload credentials and metadata."""

    upload_session_id: str = Field(..., description="Unique upload session ID")
    bucket_name: str = Field(..., description="S3/MinIO bucket name")
    bucket_region: Optional[str] = Field(None, description="Bucket region (if applicable)")
    presigned_url: str = Field(
        ..., description="Pre-signed POST URL for direct bucket uploads"
    )
    chunk_size_bytes: int = Field(
        default=5242880, description="Recommended chunk size (5MB default)"
    )
    max_chunks: int = Field(..., description="Maximum number of chunks allowed")
    expires_in_seconds: int = Field(
        default=3600, description="Session expiration time (seconds)"
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata (content-type, encryption, etc.)",
    )


class ChunkUploadNotification(BaseModel):
    """Notification when a single chunk upload completes."""

    upload_session_id: str = Field(..., description="Session ID from BucketInfoResponse")
    chunk_number: int = Field(..., ge=1, description="1-indexed chunk number")
    chunk_hash: str = Field(..., description="MD5 or SHA256 hash of chunk data")
    chunk_size_bytes: int = Field(..., gt=0)


class ChunkUploadResponse(BaseModel):
    """Response to chunk upload notification."""

    upload_session_id: str
    chunk_number: int
    status: str = Field(default="received")  # "received", "stored", "error"
    message: Optional[str] = None


class DocumentUploadCompleteRequest(BaseModel):
    """Request to complete document upload and trigger ingestion."""

    upload_session_id: str = Field(..., description="Session ID from BucketInfoResponse")
    total_chunks: int = Field(..., ge=1, description="Total number of chunks uploaded")
    file_hash: str = Field(..., description="Hash of complete file for verification")
    course_id: Optional[str] = Field(None, description="Optional course context")
    document_metadata: dict = Field(
        default_factory=dict,
        description="Custom metadata to attach to document",
    )


class DocumentUploadCompleteResponse(BaseModel):
    """Response when upload is complete and ingestion starts."""

    document_key: str = Field(..., description="S3/MinIO object key")
    ingestion_job_id: str = Field(..., description="Pipeline job ID (for tracking)")
    status: str = Field(default="queued")  # "queued", "processing", "complete"
    message: str = Field(...)


class UploadSession(BaseModel):
    """Represents an active upload session (stored in DB)."""

    upload_session_id: str
    document_name: str
    content_type: str
    total_size_bytes: int
    chunking_strategy: ChunkingStrategy
    bucket_key: str  # S3/MinIO object path
    user_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(...)
    chunks_received: set[int] = Field(default_factory=set)  # Received chunk numbers
    status: str = "active"  # "active", "complete", "failed", "expired"

