from pydantic import BaseModel, Field


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
