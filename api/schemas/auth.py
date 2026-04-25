"""Auth DTOs (AGENTS.md §5, add-jwt-auth/design.md).

Intentionally ORM-agnostic: ``UserOut`` consumes SQLAlchemy models via
``model_config = ConfigDict(from_attributes=True)`` but never imports one.

Password validation policy (AGENTS.md §6): ``≥ 8 chars``, must contain at
least one letter and one digit. Stricter rules can be added later without
breaking the wire format.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

__all__ = [
    "LoginIn",
    "RefreshIn",
    "RegisterIn",
    "TokenPair",
    "UserOut",
]

_PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


class RegisterIn(BaseModel):
    """Registration payload. Email is case-insensitive, password ≥ 8 chars."""

    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]
    display_name: Annotated[str, Field(max_length=64)] | None = None

    @field_validator("password")
    @classmethod
    def _check_strength(cls, v: str) -> str:
        if not _PASSWORD_RE.match(v):
            raise ValueError("password must contain both letters and digits")
        return v


class LoginIn(BaseModel):
    """Login payload — mirrors :class:`RegisterIn` minus ``display_name``.

    No strength validation on login; we only check credentials against the DB.
    """

    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]


class RefreshIn(BaseModel):
    """Request body for ``/auth/refresh`` and ``/auth/logout``.

    Shared because both endpoints take just the refresh token and nothing else.
    """

    refresh_token: Annotated[str, Field(min_length=16, max_length=4096)]


class TokenPair(BaseModel):
    """Response body after ``/auth/login`` and ``/auth/refresh``."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime


class UserOut(BaseModel):
    """Public user projection. Never exposes ``hashed_password``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    display_name: str | None = None
    is_active: bool
    created_at: datetime
