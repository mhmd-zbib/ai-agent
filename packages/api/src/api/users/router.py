"""User routes — registration and profile."""

from api.dependencies import get_current_user
from api.users.schemas import UserCreate, UserOut
from api.users.service import UserService
from fastapi import APIRouter, Depends, Request, status

router = APIRouter(prefix="/v1/users", tags=["users"])


def _get_user_service(request: Request) -> UserService:
    return request.app.state.user_service


@router.post(
    "/register",
    summary="Register a new user",
    description="Create a new user account with email and password.",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: UserCreate,
    user_service: UserService = Depends(_get_user_service),
) -> UserOut:
    return user_service.register_user(payload)


@router.get(
    "/me",
    summary="Get current user",
    description="Return the profile of the authenticated user.",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
)
def me(current_user: UserOut = Depends(get_current_user)) -> UserOut:
    return current_user
