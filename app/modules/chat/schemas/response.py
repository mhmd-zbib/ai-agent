from datetime import datetime

from pydantic import BaseModel


class ChatHistoryItem(BaseModel):
    role: str
    content: str
    created_at: datetime


class   ChatResponse(BaseModel):
    session_id: str
    reply: str
    history: list[ChatHistoryItem]


class StreamChunk(BaseModel):
    session_id: str
    chunk: str


class SessionResetResponse(BaseModel):
    session_id: str
    cleared: bool

