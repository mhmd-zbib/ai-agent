"""Onboarding request/response schemas."""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from common.core.enums import (
    DegreeLevel,
    DifficultyLevel,
    ExplanationStyle,
    LearningGoal,
    PreferredFormat,
    PreferredLanguage,
    StudyFrequency,
)


# ------------------------------------------------------------------
# Layer 2 — Academic context
# ------------------------------------------------------------------


class AcademicProfileIn(BaseModel):
    """Layer 2: core academic context — submitted once during onboarding."""

    model_config = {"extra": "forbid"}

    university_id: str = Field(description="University ID from /v1/universities")
    faculty_id: str | None = Field(
        default=None,
        description="Faculty ID from /v1/universities/{id}/faculties",
    )
    major_id: str = Field(description="Major ID from /v1/faculties/{id}/majors")
    degree_level: DegreeLevel = Field(description="Degree level", examples=["BS"])
    academic_year: int = Field(ge=1, le=6, description="Current academic year (1-6)", examples=[2])
    course_ids: list[str] = Field(
        default_factory=list,
        description="Course IDs from /v1/universities/{id}/courses",
    )

    @field_validator("course_ids")
    @classmethod
    def deduplicate_courses(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        return [c for c in v if not (c in seen or seen.add(c))]  # type: ignore[func-returns-value]


class AcademicProfileOut(BaseModel):
    """Academic profile — includes denormalized names for display."""

    user_id: str
    university_id: str
    university_name: str
    faculty_id: str | None
    faculty_name: str | None
    major_id: str
    major_name: str
    degree_level: DegreeLevel
    academic_year: int
    course_ids: list[str]
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------
# Layer 3 — AI personalization
# ------------------------------------------------------------------


class LearningPreferencesIn(BaseModel):
    """Layer 3: AI personalization — can be updated at any time."""

    model_config = {"extra": "forbid"}

    explanation_style: ExplanationStyle = Field(
        default=ExplanationStyle.SIMPLE,
        description="Preferred explanation style",
    )
    preferred_language: PreferredLanguage = Field(
        default=PreferredLanguage.ENGLISH,
        description="Preferred response language",
    )
    difficulty_level: DifficultyLevel = Field(
        default=DifficultyLevel.INTERMEDIATE,
        description="Preferred difficulty level",
    )
    goals: list[LearningGoal] = Field(default_factory=list, description="Learning goals")
    weak_areas: str | None = Field(
        default=None,
        max_length=500,
        description="Topics the student struggles with (free text)",
    )
    study_frequency: StudyFrequency = Field(
        default=StudyFrequency.DAILY,
        description="How often the student studies",
    )
    preferred_formats: list[PreferredFormat] = Field(
        default_factory=list,
        description="Preferred content formats",
    )


class LearningPreferencesOut(BaseModel):
    """Learning preferences response."""

    user_id: str
    explanation_style: ExplanationStyle
    preferred_language: PreferredLanguage
    difficulty_level: DifficultyLevel
    goals: list[LearningGoal]
    weak_areas: str | None
    study_frequency: StudyFrequency
    preferred_formats: list[PreferredFormat]
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------
# Status
# ------------------------------------------------------------------


class OnboardingStatus(BaseModel):
    """Overall onboarding completion status for a user."""

    user_id: str
    onboarding_complete: bool = Field(description="True once academic context is saved")
    academic_profile_complete: bool
    learning_preferences_complete: bool
