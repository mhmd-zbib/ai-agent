"""Single source of truth for all SQLAlchemy table definitions.

All repositories import from here so FK references are consistent
and checkfirst=True creation works across the whole schema.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    TIMESTAMP,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

# ------------------------------------------------------------------
# Auth / Users
# ------------------------------------------------------------------

users = Table(
    "users",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("email", String(320), nullable=False, unique=True),
    Column("display_name", String(100)),
    Column("role", String(10), nullable=False, server_default="USER"),
    Column("onboarding_complete", Boolean, nullable=False, server_default="false"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default="now()"),
)

auth_credentials = Table(
    "auth_credentials",
    metadata,
    Column(
        "user_id",
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("password_hash", Text, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default="now()"),
)

# ------------------------------------------------------------------
# Academic reference data
# ------------------------------------------------------------------

universities = Table(
    "universities",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(200), nullable=False, unique=True),
    Column("code", String(20), nullable=False, unique=True),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default="now()"),
)

faculties = Table(
    "faculties",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "university_id",
        String(36),
        ForeignKey("universities.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("name", String(200), nullable=False),
    Column("code", String(20), nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default="now()"),
    UniqueConstraint("university_id", "code", name="uq_faculties_uni_code"),
)

majors = Table(
    "majors",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "faculty_id",
        String(36),
        ForeignKey("faculties.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("name", String(200), nullable=False),
    Column("code", String(20), nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default="now()"),
    UniqueConstraint("faculty_id", "code", name="uq_majors_faculty_code"),
)

courses = Table(
    "courses",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "university_id",
        String(36),
        ForeignKey("universities.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("code", String(20), nullable=False),
    Column("name", String(200), nullable=False),
    Column("credits", SmallInteger),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default="now()"),
    UniqueConstraint("university_id", "code", name="uq_courses_uni_code"),
)

# ------------------------------------------------------------------
# Onboarding
# ------------------------------------------------------------------

student_profiles = Table(
    "student_profiles",
    metadata,
    Column(
        "user_id",
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("university_id", String(36), ForeignKey("universities.id"), nullable=False),
    Column("faculty_id", String(36), ForeignKey("faculties.id")),
    Column("major_id", String(36), ForeignKey("majors.id"), nullable=False),
    Column("degree_level", String(20), nullable=False),
    Column("academic_year", SmallInteger, nullable=False),
    Column("course_ids", JSONB, nullable=False, server_default="'[]'"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default="now()"),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default="now()"),
)

learning_preferences = Table(
    "learning_preferences",
    metadata,
    Column(
        "user_id",
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("explanation_style", String(20), nullable=False, server_default="'SIMPLE'"),
    Column("preferred_language", String(20), nullable=False, server_default="'ENGLISH'"),
    Column("difficulty_level", String(20), nullable=False, server_default="'INTERMEDIATE'"),
    Column("goals", JSONB, nullable=False, server_default="'[]'"),
    Column("weak_areas", Text),
    Column("study_frequency", String(20), nullable=False, server_default="'DAILY'"),
    Column("preferred_formats", JSONB, nullable=False, server_default="'[]'"),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default="now()"),
    Column("updated_at", TIMESTAMP(timezone=True), nullable=False, server_default="now()"),
)

# ------------------------------------------------------------------
# Memory / Chat
# ------------------------------------------------------------------

chat_messages = Table(
    "chat_messages",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("session_id", String(128), nullable=False),
    Column("message_index", Integer, nullable=False),
    Column("role", String(16), nullable=False),
    Column("content", Text, nullable=False),
    Column("created_at", TIMESTAMP(timezone=True), nullable=False, server_default="now()"),
    UniqueConstraint("session_id", "message_index", name="uq_chat_messages_session_idx"),
    CheckConstraint(
        "role IN ('system', 'user', 'assistant')", name="chk_chat_messages_role"
    ),
)

Index(
    "idx_chat_messages_session_order",
    chat_messages.c.session_id,
    chat_messages.c.message_index,
)

__all__ = [
    "metadata",
    "auth_credentials",
    "chat_messages",
    "courses",
    "faculties",
    "learning_preferences",
    "majors",
    "student_profiles",
    "universities",
    "users",
]
