from api.chat.schemas import (
    ChatRequest,
    ChatResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionResetResponse,
)
from api.chat.service import ChatService
from api.dependencies import get_chat_service, get_current_user
from api.auth.schemas import UserOut
from fastapi import APIRouter, Depends, status

router = APIRouter(
    prefix="/v1/agent",
    tags=["agent"],
    dependencies=[Depends(get_current_user)],
)


@router.post(
    "/sessions",
    summary="Create a new chat session",
    description="Initialize a new conversation session and return its ID.",
    response_model=SessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: SessionCreateRequest,
    chat_service: ChatService = Depends(get_chat_service),
) -> SessionCreateResponse:
    return chat_service.create_session(payload.course_code)


@router.post(
    "/chat",
    summary="Send a chat message",
    description="Send a user message to the agent and receive a response.",
    response_model=ChatResponse,
    response_model_exclude_none=True,
    response_model_exclude={"tool_action"},
    status_code=status.HTTP_200_OK,
)
async def chat(
    payload: ChatRequest,
    current_user: UserOut = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return chat_service.reply(
        payload,
        user_id=current_user.id,
        university_name=current_user.university,
    )


@router.delete(
    "/sessions/{session_id}",
    summary="Reset a chat session",
    description="Clear all messages from the specified session.",
    response_model=SessionResetResponse,
    status_code=status.HTTP_200_OK,
)
async def reset_session(
    session_id: str,
    chat_service: ChatService = Depends(get_chat_service),
) -> SessionResetResponse:
    return chat_service.reset_session(session_id)
