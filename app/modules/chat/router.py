from fastapi import APIRouter, Depends, status

from app.modules.chat.schemas import ChatRequest, ChatResponse, SessionCreateResponse, SessionResetResponse
from app.modules.chat.services.chat_service import ChatService
from app.shared.deps import get_chat_service, get_current_user

router = APIRouter(
    prefix="/v1/agent",
    tags=["agent"],
    dependencies=[Depends(get_current_user)],
)


@router.post("/sessions", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    chat_service: ChatService = Depends(get_chat_service),
) -> SessionCreateResponse:
    return chat_service.create_session()


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
