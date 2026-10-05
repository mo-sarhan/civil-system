"""Pydantic schemas for authentication."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Credentials for the login endpoint."""

    username: str = Field(min_length=3, max_length=80, examples=["admin"])
    password: str = Field(min_length=1, max_length=256, examples=["Str0ng!Passw0rd"])


class TokenPair(BaseModel):
    """Access + refresh tokens."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="مدة صلاحية التوكن بالثواني")


class LoginResponse(TokenPair):
    """Tokens plus the signed-in user so the UI can route immediately."""

    user: UserOut


class RefreshRequest(BaseModel):
    """Body of ``POST /auth/refresh``."""

    refresh_token: str


class UserOut(BaseModel):
    """Public representation of a user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str | None = None
    role: str
    is_active: bool
    must_change_password: bool = False
    last_login_at: datetime | None = None
    created_at: datetime | None = None


class UserCreate(BaseModel):
    """Create a user (admin only)."""

    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=1, max_length=256)
    full_name: str | None = Field(default=None, max_length=150)
    role: Literal["admin", "editor", "viewer"] = "viewer"
    is_active: bool = True
    must_change_password: bool = True


class UserUpdate(BaseModel):
    """Update a user (admin only)."""

    full_name: str | None = Field(default=None, max_length=150)
    role: Literal["admin", "editor", "viewer"] | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=1, max_length=256)


class PasswordChange(BaseModel):
    """Self-service password change."""

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


LoginResponse.model_rebuild()
