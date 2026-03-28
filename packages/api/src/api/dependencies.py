"""FastAPI dependency providers."""

from api.documents.service import DocumentUploadService
from common.core.enums import Role
from common.core.exceptions import AuthorizationError, OnboardingRequiredError
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


def get_chat_service(request: Request):  # type: ignore[return]
    return request.app.state.chat_service


def get_user_service(request: Request):  # type: ignore[return]
    return request.app.state.user_service


def get_onboarding_service(request: Request):  # type: ignore[return]
    return request.app.state.onboarding_service


def get_document_upload_service(request: Request) -> DocumentUploadService:
    return request.app.state.document_upload_service


def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_service=Depends(get_user_service),
):  # type: ignore[return]
    return user_service.get_user_from_token(token)


def require_admin(current_user=Depends(get_current_user)):  # type: ignore[return]
    """Restrict access to ADMIN role."""
    if current_user.role != Role.ADMIN:
        raise AuthorizationError("Admin access required.")
    return current_user


def require_onboarding_complete(current_user=Depends(get_current_user)):  # type: ignore[return]
    """Block access until the student has completed layer-2 onboarding."""
    if not current_user.onboarding_complete:
        raise OnboardingRequiredError(
            "Please complete student onboarding at POST /v1/onboarding/academic first."
        )
    return current_user
