from fastapi import APIRouter, Depends, status

from app.modules.users.schemas import LoginRequest, TokenResponse, UserCreate, UserOut
from app.modules.users.services.user_service import UserService
from app.shared.deps import get_current_user, get_user_service

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserCreate,
    user_service: UserService = Depends(get_user_service),
) -> UserOut:
    return user_service.register_user(payload)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    user_service: UserService = Depends(get_user_service),
) -> TokenResponse:
    return user_service.login(payload)


@router.get("/me", response_model=UserOut)
def me(current_user: UserOut = Depends(get_current_user)) -> UserOut:
    return current_user
