from pydantic import BaseModel, Field


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

