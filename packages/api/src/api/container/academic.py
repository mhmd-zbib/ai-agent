"""Academic entity service factories — universities, faculties, majors, courses, onboarding."""

from sqlalchemy.engine import Engine

from api.courses.repository import CourseRepository
from api.courses.service import CourseService
from api.faculties.repository import FacultyRepository
from api.faculties.service import FacultyService
from api.majors.repository import MajorRepository
from api.majors.service import MajorService
from api.onboarding.repository import LearningPreferencesRepository, StudentProfileRepository
from api.onboarding.service import OnboardingService
from api.universities.repository import UniversityRepository
from api.universities.service import UniversityService
from api.users.repository import UserRepository


def create_university_service(postgres_engine: Engine) -> UniversityService:
    repo = UniversityRepository(postgres_engine)
    repo.ensure_schema()
    return UniversityService(repo)


def create_faculty_service(postgres_engine: Engine) -> FacultyService:
    repo = FacultyRepository(postgres_engine)
    repo.ensure_schema()
    return FacultyService(repo)


def create_major_service(postgres_engine: Engine) -> MajorService:
    repo = MajorRepository(postgres_engine)
    repo.ensure_schema()
    return MajorService(repo)


def create_course_service(postgres_engine: Engine) -> CourseService:
    repo = CourseRepository(postgres_engine)
    repo.ensure_schema()
    return CourseService(repo)


def create_onboarding_service(
    postgres_engine: Engine,
    university_service: UniversityService,
    faculty_service: FacultyService,
    major_service: MajorService,
    course_service: CourseService,
) -> OnboardingService:
    student_repo = StudentProfileRepository(postgres_engine)
    student_repo.ensure_schema()
    prefs_repo = LearningPreferencesRepository(postgres_engine)
    prefs_repo.ensure_schema()
    return OnboardingService(
        student_profile_repo=student_repo,
        learning_prefs_repo=prefs_repo,
        user_repo=UserRepository(postgres_engine),
        university_service=university_service,
        faculty_service=faculty_service,
        major_service=major_service,
        course_service=course_service,
    )
