"""DTOs for ``/orgs`` (workspaces) and their members."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

__all__ = [
    "MemberAddIn",
    "MemberOut",
    "MemberRoleUpdateIn",
    "OrgCreateIn",
    "OrgOut",
    "OrgTransferIn",
    "OrgUpdateIn",
]


# Roles are ordered low→high in privilege; helpers below compare these.
Role = Literal["owner", "editor", "viewer"]

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class OrgCreateIn(BaseModel):
    """``POST /orgs`` body. Slug is optional — server derives one from
    the name when omitted, with a numeric suffix to disambiguate."""

    name: Annotated[str, Field(min_length=1, max_length=120)]
    slug: Annotated[str, Field(max_length=64)] | None = None

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v.startswith("personal-"):
            # Reserved namespace for the auto-provisioned per-user org.
            raise ValueError("'personal-' is a reserved slug prefix")
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be lowercase letters/digits/hyphens, "
                "1-64 chars, no leading/trailing hyphen"
            )
        return v


class OrgUpdateIn(BaseModel):
    """``PATCH /orgs/{id}`` — owner-only, name only (slug is immutable so
    URLs we ship out via wiki links don't rot)."""

    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    name: str
    owner_id: uuid.UUID
    is_personal: bool
    created_at: datetime
    updated_at: datetime
    # The caller's role in this org. Filled in by the router after the
    # membership lookup — not from the ORM.
    role: Role


class MemberAddIn(BaseModel):
    """``POST /orgs/{id}/members`` — invite an existing user by email.

    There is no "invite a stranger by email + send a sign-up link" flow
    yet; the target user must already have an account. Returns 404 if
    the email doesn't resolve.
    """

    email: EmailStr
    role: Role = "editor"


class MemberRoleUpdateIn(BaseModel):
    """``PATCH /orgs/{id}/members/{user_id}`` — change a member's role."""

    role: Role


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    email: str
    display_name: str | None
    role: Role
    created_at: datetime


class OrgTransferIn(BaseModel):
    """``POST /orgs/{id}/transfer`` body — make another member the owner.

    The previous owner is demoted to ``editor`` (they keep write access
    but lose admin powers). The target must already be a member.
    """

    new_owner_id: uuid.UUID
