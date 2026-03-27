"""FastAPI dependency providers."""

from api.auth.schemas import UserOut
from api.auth.service import UserService
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/users/login")


def get_chat_service(request: Request):
    return request.app.state.chat_service


def get_user_service(request: Request) -> UserService:
    return request.app.state.user_service


def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_service: UserService = Depends(get_user_service),
) -> UserOut:
    return user_service.get_user_from_token(token)
