"""Major request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class MajorIn(BaseModel):
    model_config = {"extra": "forbid"}

    faculty_id: str = Field(description="Parent faculty ID")
    name: str = Field(max_length=200, examples=["Computer Science"])
    code: str = Field(max_length=20, examples=["CS"])


class MajorOut(BaseModel):
    id: str
    faculty_id: str
    name: str
    code: str
    is_active: bool
    created_at: datetime
