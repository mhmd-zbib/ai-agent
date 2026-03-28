"""Admin routes — user management.

All routes require the ADMIN role.
"""

from api.admin.service import AdminService
from api.dependencies import require_admin
from api.users.schemas import AdminUpdateRole, UserOut
from fastapi import APIRouter, Depends, Query, Request, status

router = APIRouter(prefix="/v1/admin", tags=["admin"])


def _get_admin_service(request: Request) -> AdminService:
    return request.app.state.admin_service


@router.get(
    "/users",
    summary="List all users (admin)",
    description="Return a paginated list of all registered users.",
    response_model=list[UserOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
def list_users(
    limit: int = Query(default=20, ge=1, le=100, description="Page size"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    admin_service: AdminService = Depends(_get_admin_service),
) -> list[UserOut]:
    return admin_service.list_users(limit=limit, offset=offset)


@router.put(
    "/users/{user_id}/role",
    summary="Update user role (admin)",
    description="Change the role of any user.",
    response_model=UserOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
def update_role(
    user_id: str,
    payload: AdminUpdateRole,
    admin_service: AdminService = Depends(_get_admin_service),
) -> UserOut:
    return admin_service.update_user_role(user_id, payload)
