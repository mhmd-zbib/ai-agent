from api.auth.schemas import LoginRequest, TokenResponse
from api.users.service import UserService
from fastapi import APIRouter, Depends, Request, status

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _get_user_service(request: Request) -> UserService:
    return request.app.state.user_service


@router.post(
    "/login",
    summary="Authenticate a user",
    description="Validate credentials and return a JWT access token.",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def login(
    payload: LoginRequest,
    user_service: UserService = Depends(_get_user_service),
) -> TokenResponse:
    return user_service.login(payload)
