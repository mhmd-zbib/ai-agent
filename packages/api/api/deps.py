# Backward-compat shim — moved to api.dependencies
from api.dependencies import get_chat_service, get_current_user, get_user_service, oauth2_scheme
from api.auth.schemas import UserOut
from api.auth.service import UserService
from api.chat.service import ChatService

__all__ = [
    "get_chat_service",
    "get_user_service",
    "get_current_user",
    "oauth2_scheme",
    "UserOut",
    "UserService",
    "ChatService",
]
