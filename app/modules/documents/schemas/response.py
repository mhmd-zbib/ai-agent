from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    upload_id: str = Field(description="Generated ID for this upload")
    bucket: str = Field(description="Bucket that stores document chunks")
    object_prefix: str = Field(description="Object key prefix for this upload")
    manifest_key: str = Field(description="Object key where upload manifest is stored")

    chunk_size_bytes: int = Field(gt=0)
    chunk_count: int = Field(ge=0)
    total_size_bytes: int = Field(ge=0)

    event_id: str = Field(description="Event ID pushed to RabbitMQ")
    event_published: bool = Field(default=True)

