"""Pydantic request/response schemas for the upload endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from shared.enums import University


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class UploadInitiateRequest(BaseModel):
    """Body for POST /v1/uploads — kick off a multipart upload."""

    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(min_length=1, description="Original file name, e.g. lecture1.pdf")
    content_type: str | None = Field(default=None, description="MIME type, e.g. application/pdf")
    file_size_bytes: int = Field(gt=0, description="Total file size in bytes")
    chunk_size_bytes: int | None = Field(
        default=None,
        gt=0,
        description="Desired chunk size in bytes; server picks a default when omitted",
    )


class ChunkInfo(BaseModel):
    """Metadata for a single uploaded chunk — sent by the client in the complete request."""

    model_config = ConfigDict(extra="forbid")

    chunk_index: int = Field(ge=0, description="Zero-based chunk index")
    size_bytes: int = Field(gt=0, description="Actual size of this chunk in bytes")


class UploadCompleteRequest(BaseModel):
    """Body for POST /v1/uploads/{upload_id}/complete — confirm all chunks are in MinIO."""

    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(min_length=1, description="Original file name")
    content_type: str | None = Field(default=None, description="MIME type")
    chunks: list[ChunkInfo] = Field(min_length=1, description="Metadata for every uploaded chunk")
    course_code: str = Field(min_length=1, description="Course code the document belongs to")
    university_name: University = Field(description="University the document belongs to")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class ChunkUploadUrl(BaseModel):
    """Presigned PUT URL for a single chunk — returned by the initiate endpoint."""

    chunk_index: int = Field(ge=0)
    object_key: str = Field(description="MinIO object key for this chunk")
    presigned_url: str = Field(description="Presigned PUT URL valid for 1 hour")


class UploadInitiateResponse(BaseModel):
    """Response from POST /v1/uploads — includes presigned URLs for each chunk."""

    upload_id: str = Field(description="Logical upload identifier (UUID)")
    bucket: str = Field(description="MinIO bucket name")
    object_prefix: str = Field(description="Common object key prefix for all chunks")
    chunk_size_bytes: int = Field(gt=0, description="Target chunk size in bytes")
    chunk_count: int = Field(ge=1, description="Total number of chunks")
    chunks: list[ChunkUploadUrl] = Field(description="Presigned URL for each chunk")


class UploadCompleteResponse(BaseModel):
    """Response from POST /v1/uploads/{upload_id}/complete."""

    upload_id: str = Field(description="The upload ID that was completed")
    document_id: str = Field(description="Newly created document record UUID")
    event_id: str = Field(description="Unique ID of the published DocumentUploadedEvent")
    event_published: bool = Field(default=True, description="Whether the event was published to the broker")


# ---------------------------------------------------------------------------
# Event schema
# ---------------------------------------------------------------------------


class DocumentUploadedEvent(BaseModel):
    """Event published to RabbitMQ after a successful upload completion."""

    event_id: str = Field(description="Unique event identifier")
    event_type: Literal["document.uploaded"] = "document.uploaded"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    document_id: str = Field(description="Postgres document record UUID")
    upload_id: str = Field(description="Logical upload identifier")
    user_id: str | None = Field(default=None, description="Authenticated uploader ID")
    file_name: str = Field(description="Original file name")
    content_type: str | None = Field(default=None, description="MIME type")

    bucket: str = Field(description="MinIO bucket that holds the chunks")
    object_prefix: str = Field(description="Object key prefix for all chunks")
    manifest_key: str = Field(description="Object key of the uploaded manifest JSON")

    chunk_count: int = Field(ge=0, description="Number of uploaded chunks")
    total_size_bytes: int = Field(ge=0, description="Total document size in bytes")

    course_code: str = Field(description="Course code the document belongs to")
    university_name: University = Field(description="University the document belongs to")
