from pydantic import BaseModel, Field


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
