from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.shared.schemas import ResponseMetadata, ToolAction


class SessionCreateResponse(BaseModel):
    session_id: str


class ChatResponse(BaseModel):
    """
    Chat response with structured AI response data.
    
    Supports two response modes:
    - "chat": Normal conversational response (tool_action and metadata optional)
    - "tool_call": Structured response with tool actions (tool_action and metadata required for tool/mixed types)
    
    Attributes:
        session_id: Session identifier
        response_mode: Indicates if this is a normal chat or tool call response
        type: Response type - "text", "tool", or "mixed"
        content: Human-readable explanation or summary
        tool_action: Optional tool/action to execute (required for tool/mixed types in tool_call mode)
        metadata: Response metadata including confidence and sources (optional in chat mode)
    """
    session_id: str
    response_mode: Literal["chat", "tool_call"] = Field(
        default="chat",
        description="Response mode: 'chat' for normal conversation, 'tool_call' for structured tool responses"
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

