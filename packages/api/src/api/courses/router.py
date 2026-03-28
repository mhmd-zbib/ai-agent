"""Course routes.

POST endpoints require the ADMIN role.
"""

from api.dependencies import require_admin
from api.courses.schemas import CourseIn, CourseOut
from api.courses.service import CourseService
from fastapi import APIRouter, Depends, Request, status

router = APIRouter(prefix="/v1/courses", tags=["courses"])


def _get_course_service(request: Request) -> CourseService:
    return request.app.state.course_service


@router.post(
    "",
    summary="Create a course (admin)",
    description="Add a new course under a university.",
    response_model=CourseOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def create_course(
    payload: CourseIn,
    course_service: CourseService = Depends(_get_course_service),
) -> CourseOut:
    return course_service.create(payload)
