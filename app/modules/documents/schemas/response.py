from pydantic import BaseModel, Field


class ChunkUploadUrl(BaseModel):
    chunk_index: int = Field(ge=0)
    object_key: str
    presigned_url: str


class UploadInitiateResponse(BaseModel):
    upload_id: str
    bucket: str
    object_prefix: str
    chunk_size_bytes: int = Field(gt=0)
    chunk_count: int = Field(ge=1)
    chunks: list[ChunkUploadUrl]


class UploadCompleteResponse(BaseModel):
    upload_id: str
    event_id: str
    event_published: bool = True
