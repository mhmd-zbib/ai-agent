from typing import Optional

from pydantic import BaseModel

from app.shared.schemas import ResponseMetadata, ToolAction


class SessionCreateResponse(BaseModel):
    session_id: str


class ChatResponse(BaseModel):
    """
    Chat response with structured AI response data.
    
    Attributes:
        session_id: Session identifier
        type: Response type - "text", "tool", or "mixed"
        content: Human-readable explanation or summary
        tool_action: Optional tool/action to execute
        metadata: Response metadata including confidence and sources
    """
    session_id: str
    type: str
    content: str
    tool_action: Optional[ToolAction] = None
    metadata: ResponseMetadata


class StreamChunk(BaseModel):
    session_id: str
    chunk: str


class SessionResetResponse(BaseModel):
    session_id: str
    cleared: bool

