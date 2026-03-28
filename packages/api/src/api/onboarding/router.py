"""Onboarding routes — academic context (layer 2) and AI personalization (layer 3)."""

from api.dependencies import get_current_user
from api.onboarding.schemas import (
    AcademicProfileIn,
    AcademicProfileOut,
    LearningPreferencesIn,
    LearningPreferencesOut,
    OnboardingStatus,
)
from api.onboarding.service import OnboardingService
from api.users.schemas import UserOut
from fastapi import APIRouter, Depends, Request, status

router = APIRouter(prefix="/v1/onboarding", tags=["onboarding"])


def _get_onboarding_service(request: Request) -> OnboardingService:
    return request.app.state.onboarding_service


# ------------------------------------------------------------------
# Status
# ------------------------------------------------------------------


@router.get(
    "/status",
    summary="Get onboarding status",
    description="Returns which onboarding layers the user has completed.",
    response_model=OnboardingStatus,
    status_code=status.HTTP_200_OK,
)
def get_status(
    current_user: UserOut = Depends(get_current_user),
    onboarding_service: OnboardingService = Depends(_get_onboarding_service),
) -> OnboardingStatus:
    return onboarding_service.get_status(current_user.id)


# ------------------------------------------------------------------
# Layer 2 — Academic context (mandatory, unlocks chat)
# ------------------------------------------------------------------


@router.post(
    "/academic",
    summary="Submit academic context",
    description=(
        "Saves university, major, degree, year and current courses. "
        "Completing this layer unlocks the chat endpoint."
    ),
    response_model=AcademicProfileOut,
    status_code=status.HTTP_200_OK,
)
def submit_academic_profile(
    payload: AcademicProfileIn,
    current_user: UserOut = Depends(get_current_user),
    onboarding_service: OnboardingService = Depends(_get_onboarding_service),
) -> AcademicProfileOut:
    return onboarding_service.submit_academic_profile(current_user.id, payload)


@router.get(
    "/academic",
    summary="Get academic profile",
    description="Returns the student's saved academic context.",
    response_model=AcademicProfileOut | None,
    status_code=status.HTTP_200_OK,
)
def get_academic_profile(
    current_user: UserOut = Depends(get_current_user),
    onboarding_service: OnboardingService = Depends(_get_onboarding_service),
) -> AcademicProfileOut | None:
    return onboarding_service.get_academic_profile(current_user.id)


# ------------------------------------------------------------------
# Layer 3 — AI personalization (optional, improves AI quality)
# ------------------------------------------------------------------


@router.post(
    "/preferences",
    summary="Submit learning preferences",
    description="Saves AI personalization settings (style, goals, formats). Optional.",
    response_model=LearningPreferencesOut,
    status_code=status.HTTP_200_OK,
)
def submit_learning_preferences(
    payload: LearningPreferencesIn,
    current_user: UserOut = Depends(get_current_user),
    onboarding_service: OnboardingService = Depends(_get_onboarding_service),
) -> LearningPreferencesOut:
    return onboarding_service.submit_learning_preferences(current_user.id, payload)


@router.get(
    "/preferences",
    summary="Get learning preferences",
    description="Returns the student's saved AI personalization settings.",
    response_model=LearningPreferencesOut | None,
    status_code=status.HTTP_200_OK,
)
def get_learning_preferences(
    current_user: UserOut = Depends(get_current_user),
    onboarding_service: OnboardingService = Depends(_get_onboarding_service),
) -> LearningPreferencesOut | None:
    return onboarding_service.get_learning_preferences(current_user.id)
