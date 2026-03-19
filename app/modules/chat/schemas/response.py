from pydantic import BaseModel


class SessionCreateResponse(BaseModel):
    session_id: str


class ChatResponse(BaseModel):
    session_id: str
    reply: str


class StreamChunk(BaseModel):
    session_id: str
    chunk: str


class SessionResetResponse(BaseModel):
    session_id: str
    cleared: bool

