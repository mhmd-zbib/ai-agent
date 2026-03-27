from typing import Literal, Optional

from pydantic import BaseModel, Field
from shared.schemas import ResponseMetadata, ToolAction


class SessionCreateRequest(BaseModel):
    course_code: str = Field(default="", max_length=50)


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=8000)
    use_rag: bool = False


class SessionCreateResponse(BaseModel):
    session_id: str


class ChatResponse(BaseModel):
    """Chat response with structured AI response data."""

    session_id: str
    response_mode: Literal["chat", "tool_call"] = Field(
        default="chat",
        description="Response mode: 'chat' for normal conversation, 'tool_call' for structured tool responses",
    )
    type: str
    content: str
    tool_action: Optional[ToolAction] = None
    metadata: Optional[ResponseMetadata] = None


class StreamChunk(BaseModel):
    session_id: str
    chunk: str


class SessionResetResponse(BaseModel):
    session_id: str
    cleared: bool
