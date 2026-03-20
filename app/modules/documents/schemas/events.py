from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class DocumentUploadedEvent(BaseModel):
    event_id: str = Field(description="Unique ID for this emitted event")
    event_type: Literal["document.uploaded"] = "document.uploaded"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    upload_id: str = Field(description="Logical upload ID")
    user_id: str | None = Field(default=None, description="Authenticated uploader ID")
    file_name: str = Field(description="Original file name")
    content_type: str | None = Field(default=None, description="Uploaded MIME type")

    bucket: str = Field(description="Target MinIO bucket")
    object_prefix: str = Field(description="Prefix that holds chunk objects")
    manifest_key: str = Field(description="Manifest object key")
    chunk_keys: list[str] = Field(default_factory=list, description="Uploaded chunk object keys")

    chunk_size_bytes: int = Field(gt=0, description="Configured upload chunk size")
    chunk_count: int = Field(ge=0, description="Number of chunks written")
    total_size_bytes: int = Field(ge=0, description="Total uploaded bytes")

