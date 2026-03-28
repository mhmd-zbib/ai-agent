"""Major routes.

POST endpoints require the ADMIN role.
"""

from api.dependencies import require_admin
from api.majors.schemas import MajorIn, MajorOut
from api.majors.service import MajorService
from fastapi import APIRouter, Depends, Request, status

router = APIRouter(prefix="/v1/majors", tags=["majors"])


def _get_major_service(request: Request) -> MajorService:
    return request.app.state.major_service


@router.post(
    "",
    summary="Create a major (admin)",
    description="Add a new major under a faculty.",
    response_model=MajorOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_major(
    payload: MajorIn,
    major_service: MajorService = Depends(_get_major_service),
) -> MajorOut:
    return major_service.create(payload)
