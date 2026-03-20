from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from app.modules.chat.services.chat_service import ChatService
from app.modules.documents.services import DocumentService
from app.modules.users.schemas import UserOut
from app.modules.users.services.user_service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/users/login")


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


def get_user_service(request: Request) -> UserService:
    return request.app.state.user_service


def get_document_service(request: Request) -> DocumentService:
    return request.app.state.document_service


def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_service: UserService = Depends(get_user_service),
) -> UserOut:
    return user_service.get_user_from_token(token)
