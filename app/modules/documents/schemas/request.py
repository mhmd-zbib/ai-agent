from pydantic import BaseModel, Field

from app.shared.enums import University


class UploadInitiateRequest(BaseModel):
    file_name: str = Field(min_length=1)
    content_type: str | None = None
    file_size_bytes: int = Field(gt=0)
    chunk_size_bytes: int | None = Field(default=None, gt=0)


class ChunkInfo(BaseModel):
    chunk_index: int = Field(ge=0)
    size_bytes: int = Field(gt=0)


class UploadCompleteRequest(BaseModel):
    file_name: str = Field(min_length=1)
    content_type: str | None = None
    chunks: list[ChunkInfo] = Field(min_length=1)
    course_code: str = Field(
        min_length=1, description="Course code the document belongs to"
    )
    university_name: University = Field(
        description="University the document belongs to"
    )
