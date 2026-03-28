"""Faculty routes.

GET endpoints require any authenticated user.
POST endpoints require the ADMIN role.
"""

from api.dependencies import get_current_user, require_admin
from api.faculties.schemas import FacultyIn, FacultyOut
from api.faculties.service import FacultyService
from api.majors.schemas import MajorOut
from api.majors.service import MajorService
from fastapi import APIRouter, Depends, Request, status

router = APIRouter(prefix="/v1/faculties", tags=["faculties"])


def _get_faculty_service(request: Request) -> FacultyService:
    return request.app.state.faculty_service


def _get_major_service(request: Request) -> MajorService:
    return request.app.state.major_service


@router.post(
    "",
    summary="Create a faculty (admin)",
    description="Add a new faculty under a university.",
    response_model=FacultyOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_faculty(
    payload: FacultyIn,
    faculty_service: FacultyService = Depends(_get_faculty_service),
) -> FacultyOut:
    return faculty_service.create(payload)


@router.get(
    "/{faculty_id}/majors",
    summary="List majors for a faculty",
    description="Returns active majors for the given faculty.",
    response_model=list[MajorOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
def list_majors(
    faculty_id: str,
    major_service: MajorService = Depends(_get_major_service),
) -> list[MajorOut]:
    return major_service.list_by_faculty(faculty_id)
