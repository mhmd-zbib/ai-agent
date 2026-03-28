"""Faculty request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class FacultyIn(BaseModel):
    model_config = {"extra": "forbid"}

    university_id: str = Field(description="Parent university ID")
    name: str = Field(max_length=200, examples=["Faculty of Engineering"])
    code: str = Field(max_length=20, examples=["ENG"])


class FacultyOut(BaseModel):
    id: str
    university_id: str
    name: str
    code: str
    is_active: bool
    created_at: datetime
