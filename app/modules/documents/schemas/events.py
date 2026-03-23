from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.shared.enums import University


class DocumentUploadedEvent(BaseModel):
    event_id: str = Field(description="Unique ID for this emitted event")
    event_type: Literal["document.uploaded"] = "document.uploaded"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    document_id: str = Field(description="Postgres documents.document_id (UUID)")
    upload_id: str = Field(description="Logical upload ID")
    user_id: str | None = Field(default=None, description="Authenticated uploader ID")
    file_name: str = Field(description="Original file name")
    content_type: str | None = Field(default=None, description="Uploaded MIME type")

    bucket: str = Field(description="Target MinIO bucket")
    object_prefix: str = Field(description="Prefix that holds chunk objects")
    manifest_key: str = Field(
        description="Manifest object key — worker reads this to locate chunks"
    )

    chunk_count: int = Field(ge=0)
    total_size_bytes: int = Field(ge=0)

    course_code: str = Field(description="Course code the document belongs to")
    university_name: University = Field(
        description="University the document belongs to"
    )
