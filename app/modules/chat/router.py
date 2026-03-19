from fastapi import APIRouter, Depends

from app.modules.chat.schemas import ChatRequest, ChatResponse, SessionResetResponse
from app.modules.chat.services.chat_service import ChatService
from app.shared.deps import get_chat_service

router = APIRouter(prefix="/v1/agent", tags=["agent"])


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return chat_service.reply(payload)


@router.delete("/sessions/{session_id}", response_model=SessionResetResponse)
async def reset_session(
    session_id: str,
    chat_service: ChatService = Depends(get_chat_service),
) -> SessionResetResponse:
    return chat_service.reset_session(session_id)

