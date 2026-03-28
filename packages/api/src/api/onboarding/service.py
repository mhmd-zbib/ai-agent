"""Onboarding service — coordinates academic context and AI personalization."""

from api.courses.service import CourseService
from api.faculties.service import FacultyService
from api.majors.service import MajorService
from api.onboarding.repository import LearningPreferencesRepository, StudentProfileRepository
from api.onboarding.schemas import (
    AcademicProfileIn,
    AcademicProfileOut,
    LearningPreferencesIn,
    LearningPreferencesOut,
    OnboardingStatus,
)
from api.universities.service import UniversityService
from api.users.repository import UserRepository
from common.core.exceptions import NotFoundError


class OnboardingService:
    """
    Manages the two-layer student onboarding flow.

    Layer 2 (academic context) is mandatory — completing it sets
    users.onboarding_complete = TRUE and unlocks the chat endpoint.
    IDs are validated against reference data before saving.

    Layer 3 (AI personalization) is optional and can be updated any time.
    """

    def __init__(
        self,
        student_profile_repo: StudentProfileRepository,
        learning_prefs_repo: LearningPreferencesRepository,
        user_repo: UserRepository,
        university_service: UniversityService,
        faculty_service: FacultyService,
        major_service: MajorService,
        course_service: CourseService,
    ) -> None:
        self._student_repo = student_profile_repo
        self._prefs_repo = learning_prefs_repo
        self._user_repo = user_repo
        self._uni = university_service
        self._fac = faculty_service
        self._maj = major_service
        self._crs = course_service

    # ------------------------------------------------------------------
    # Layer 2 — Academic context
    # ------------------------------------------------------------------

    def submit_academic_profile(
        self, user_id: str, payload: AcademicProfileIn
    ) -> AcademicProfileOut:
        """Validate IDs, upsert profile, mark onboarding complete."""
        self._validate_academic_context(payload)
        profile = self._student_repo.upsert(user_id, payload)
        self._user_repo.mark_onboarding_complete(user_id)
        return profile

    def get_academic_profile(self, user_id: str) -> AcademicProfileOut | None:
        return self._student_repo.get(user_id)

    # ------------------------------------------------------------------
    # Layer 3 — AI personalization
    # ------------------------------------------------------------------

    def submit_learning_preferences(
        self, user_id: str, payload: LearningPreferencesIn
    ) -> LearningPreferencesOut:
        return self._prefs_repo.upsert(user_id, payload)

    def get_learning_preferences(self, user_id: str) -> LearningPreferencesOut | None:
        return self._prefs_repo.get(user_id)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self, user_id: str) -> OnboardingStatus:
        academic = self._student_repo.get(user_id)
        prefs = self._prefs_repo.get(user_id)
        return OnboardingStatus(
            user_id=user_id,
            onboarding_complete=academic is not None,
            academic_profile_complete=academic is not None,
            learning_preferences_complete=prefs is not None,
        )

    # ------------------------------------------------------------------
    # Private — validation
    # ------------------------------------------------------------------

    def _validate_academic_context(self, payload: AcademicProfileIn) -> None:
        """Raise NotFoundError if any referenced entity doesn't exist or is mismatched."""
        self._uni.get(payload.university_id)  # raises NotFoundError if missing

        if payload.faculty_id:
            fac = self._fac.get(payload.faculty_id)
            if fac.university_id != payload.university_id:
                raise NotFoundError("Faculty does not belong to the given university")

        maj = self._maj.get(payload.major_id)
        if payload.faculty_id and maj.faculty_id != payload.faculty_id:
            raise NotFoundError("Major does not belong to the given faculty")

        for course_id in payload.course_ids:
            crs = self._crs.get(course_id)
            if crs.university_id != payload.university_id:
                raise NotFoundError(f"Course '{course_id}' does not belong to this university")
