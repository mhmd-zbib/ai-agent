"""Course request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class CourseIn(BaseModel):
    model_config = {"extra": "forbid"}

    university_id: str = Field(description="University this course belongs to")
    code: str = Field(max_length=20, description="Course code", examples=["CS201"])
    name: str = Field(max_length=200, description="Full course name", examples=["Data Structures"])
    credits: int | None = Field(default=None, ge=1, le=6, description="Credit hours")


class CourseOut(BaseModel):
    id: str
    university_id: str
    code: str
    name: str
    credits: int | None
    is_active: bool
    created_at: datetime
