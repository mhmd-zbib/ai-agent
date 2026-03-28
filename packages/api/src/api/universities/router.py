"""University routes.

GET endpoints require any authenticated user (onboarding dropdowns).
POST/DELETE endpoints require the ADMIN role.
"""

from api.dependencies import get_current_user, require_admin
from api.faculties.schemas import FacultyOut
from api.faculties.service import FacultyService
from api.courses.schemas import CourseOut
from api.courses.service import CourseService
from api.universities.schemas import UniversityIn, UniversityOut
from api.universities.service import UniversityService
from fastapi import APIRouter, Depends, Request, status

router = APIRouter(prefix="/v1/universities", tags=["universities"])


def _get_university_service(request: Request) -> UniversityService:
    return request.app.state.university_service


def _get_faculty_service(request: Request) -> FacultyService:
    return request.app.state.faculty_service


def _get_course_service(request: Request) -> CourseService:
    return request.app.state.course_service


@router.get(
    "",
    summary="List active universities",
    description="Returns all active universities. Available to any authenticated user.",
    response_model=list[UniversityOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
def list_universities(
    university_service: UniversityService = Depends(_get_university_service),
) -> list[UniversityOut]:
    return university_service.list_active()


@router.post(
    "",
    summary="Create a university (admin)",
    description="Add a new university to the platform.",
    response_model=UniversityOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_university(
    payload: UniversityIn,
    university_service: UniversityService = Depends(_get_university_service),
) -> UniversityOut:
    return university_service.create(payload)


@router.delete(
    "/{university_id}",
    summary="Deactivate a university (admin)",
    description="Soft-delete a university (sets is_active=False).",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
def deactivate_university(
    university_id: str,
    university_service: UniversityService = Depends(_get_university_service),
) -> None:
    university_service.deactivate(university_id)


@router.get(
    "/{university_id}/faculties",
    summary="List faculties for a university",
    description="Returns active faculties for the given university.",
    response_model=list[FacultyOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
def list_faculties(
    university_id: str,
    faculty_service: FacultyService = Depends(_get_faculty_service),
) -> list[FacultyOut]:
    return faculty_service.list_by_university(university_id)


@router.get(
    "/{university_id}/courses",
    summary="List courses for a university",
    description="Returns active courses for the given university.",
    response_model=list[CourseOut],
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(get_current_user)],
)
def list_courses(
    university_id: str,
    course_service: CourseService = Depends(_get_course_service),
) -> list[CourseOut]:
    return course_service.list_by_university(university_id)
