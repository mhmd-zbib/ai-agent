from pydantic import BaseModel, Field
from shared.enums import Major, University


class UserCreate(BaseModel):
    """Request schema for user registration."""

    email: str = Field(
        min_length=3,
        max_length=320,
        description="User's email address",
        examples=["user@example.com"],
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="User's password (8-128 characters)",
        examples=["SecurePassword123!"],
    )
    university: University = Field(
        description="Student's university",
        examples=["LIU"],
    )
    major: Major = Field(
        description="Student's major",
        examples=["COMPUTER_SCIENCE"],
    )


class LoginRequest(BaseModel):
    """Request schema for user login."""

    email: str = Field(
        min_length=3,
        max_length=320,
        description="User's email address",
        examples=["user@example.com"],
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description="User's password",
        examples=["SecurePassword123!"],
    )


class UserOut(BaseModel):
    """Response schema for user information (without sensitive data)."""

    id: str = Field(
        description="Unique user identifier (UUID)",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    email: str = Field(
        description="User's email address",
        examples=["user@example.com"],
    )
    university: University = Field(
        description="Student's university",
        examples=["LIU"],
    )
    major: Major = Field(
        description="Student's major",
        examples=["COMPUTER_SCIENCE"],
    )


class TokenResponse(BaseModel):
    """Response schema for authentication token."""

    access_token: str = Field(
        description="JWT access token for API authentication",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."],
    )
    token_type: str = Field(
        default="bearer",
        description="Token type (always 'bearer' for JWT)",
        examples=["bearer"],
    )
