from pydantic import BaseModel, Field
from common.core.enums import Role


class UserCreate(BaseModel):
    """Minimal registration payload — no academic context (collected during onboarding)."""

    model_config = {"extra": "forbid"}

    email: str = Field(
        min_length=3,
        max_length=320,
        description="User's email address",
        examples=["user@example.com"],
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="Password (8-128 characters)",
        examples=["SecurePassword123!"],
    )
    display_name: str | None = Field(
        default=None,
        max_length=100,
        description="Optional display name",
        examples=["Alice"],
    )


class UserOut(BaseModel):
    """Public user representation — no secrets."""

    id: str = Field(
        description="Unique user identifier (UUID)",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    email: str = Field(
        description="User's email address",
        examples=["user@example.com"],
    )
    display_name: str | None = Field(
        description="Display name (optional)",
        examples=["Alice"],
    )
    role: Role = Field(
        description="Access role",
        examples=["USER"],
    )
    onboarding_complete: bool = Field(
        description="Whether the student onboarding flow has been completed",
        examples=[False],
    )


class AdminUpdateRole(BaseModel):
    """Admin request to change a user's role."""

    model_config = {"extra": "forbid"}

    role: Role = Field(
        description="New role to assign",
        examples=["ADMIN"],
    )
