"""University request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class UniversityIn(BaseModel):
    model_config = {"extra": "forbid"}

    name: str = Field(max_length=200, description="Full university name", examples=["Lebanese International University"])
    code: str = Field(max_length=20, description="Short identifier", examples=["LIU"])


class UniversityOut(BaseModel):
    id: str
    name: str
    code: str
    is_active: bool
    created_at: datetime
