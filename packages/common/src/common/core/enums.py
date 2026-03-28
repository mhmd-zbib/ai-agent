from enum import StrEnum


class Role(StrEnum):
    USER = "USER"
    ADMIN = "ADMIN"


# ------------------------------------------------------------------
# Onboarding — academic context
# ------------------------------------------------------------------


class DegreeLevel(StrEnum):
    BS = "BS"
    MS = "MS"
    PHD = "PHD"


# ------------------------------------------------------------------
# Onboarding — AI personalization
# ------------------------------------------------------------------


class ExplanationStyle(StrEnum):
    SIMPLE = "SIMPLE"
    DETAILED = "DETAILED"
    STEP_BY_STEP = "STEP_BY_STEP"


class PreferredLanguage(StrEnum):
    ENGLISH = "ENGLISH"
    ARABIC = "ARABIC"
    BILINGUAL = "BILINGUAL"


class DifficultyLevel(StrEnum):
    BASIC = "BASIC"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"


class LearningGoal(StrEnum):
    PASS_EXAMS = "PASS_EXAMS"
    DEEP_UNDERSTANDING = "DEEP_UNDERSTANDING"
    GPA_BOOST = "GPA_BOOST"
    HOMEWORK_HELP = "HOMEWORK_HELP"


class StudyFrequency(StrEnum):
    DAILY = "DAILY"
    FEW_TIMES_WEEK = "FEW_TIMES_WEEK"
    WEEKLY = "WEEKLY"
    AS_NEEDED = "AS_NEEDED"


class PreferredFormat(StrEnum):
    NOTES = "NOTES"
    FLASHCARDS = "FLASHCARDS"
    PRACTICE_PROBLEMS = "PRACTICE_PROBLEMS"
    SUMMARIES = "SUMMARIES"
