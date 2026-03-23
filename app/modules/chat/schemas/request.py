from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    course_code: str = Field(default="", max_length=50)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=8000)
    use_rag: bool = False
