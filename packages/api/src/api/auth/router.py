from api.auth.schemas import LoginRequest, TokenResponse, UserCreate, UserOut
from api.auth.service import UserService
from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordBearer

router = APIRouter(prefix="/v1/users", tags=["users"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/users/login")


def get_user_service(request: Request) -> UserService:
    return request.app.state.user_service


def get_current_user(
    token: str = Depends(oauth2_scheme),
    user_service: UserService = Depends(get_user_service),
) -> UserOut:
    return user_service.get_user_from_token(token)


@router.post(
    "/register",
    summary="Register a new user",
    description="Create a new user account with email, password, university and major.",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: UserCreate,
    user_service: UserService = Depends(get_user_service),
) -> UserOut:
    return user_service.register_user(payload)


@router.post(
    "/login",
    summary="Authenticate a user",
    description="Validate credentials and return a JWT access token.",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
def login(
    payload: LoginRequest,
    user_service: UserService = Depends(get_user_service),
) -> TokenResponse:
    return user_service.login(payload)


@router.get(
    "/me",
    summary="Get current user",
    description="Return the profile of the authenticated user.",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
)
def me(current_user: UserOut = Depends(get_current_user)) -> UserOut:
    return current_user
