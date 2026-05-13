"""DTOs for ``/orgs/{id}/wikis``, ``/wikis/{id}``, ``/wikis/{id}/pages``
and ``/wiki-pages/{id}`` (the post-Wiki-layer URL space).

Hierarchy:

    Workspace (Org) → Wiki (knowledge base) → Page
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

__all__ = [
    "WikiCreateIn",
    "WikiMemberAddIn",
    "WikiMemberOut",
    "WikiMemberRoleUpdateIn",
    "WikiOut",
    "WikiPageCreateIn",
    "WikiPageDetailOut",
    "WikiPageListOut",
    "WikiPageMoveIn",
    "WikiPageUpdateIn",
    "WikiUpdateIn",
    "WikiVisibility",
]

WikiVisibility = Literal["org_wide", "private"]
WikiRole = Literal["editor", "viewer"]

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


class WikiCreateIn(BaseModel):
    """``POST /orgs/{id}/wikis`` — create a wiki inside the workspace."""

    name: Annotated[str, Field(min_length=1, max_length=120)]
    slug: Annotated[str, Field(max_length=64)] | None = None
    description: Annotated[str, Field(max_length=500)] | None = None
    visibility: WikiVisibility = "org_wide"

    @field_validator("slug")
    @classmethod
    def _check_slug(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v == "default":
            # ``default`` is reserved for the auto-provisioned wiki.
            raise ValueError("'default' is a reserved slug")
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be lowercase letters/digits/hyphens, "
                "1-64 chars, no leading/trailing hyphen"
            )
        return v


class WikiUpdateIn(BaseModel):
    """``PATCH /wikis/{id}`` — name / description / visibility (slug is
    immutable so previously-shared wiki URLs don't rot)."""

    name: Annotated[str, Field(min_length=1, max_length=120)] | None = None
    description: Annotated[str, Field(max_length=500)] | None = None
    visibility: WikiVisibility | None = None


class WikiOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    slug: str
    name: str
    description: str | None
    created_by_user_id: uuid.UUID
    is_default: bool
    visibility: WikiVisibility
    created_at: datetime
    updated_at: datetime
    # Caller's effective role in this wiki — derived per request from
    # the combo of org role + wiki_members + visibility.
    role: Literal["owner", "editor", "viewer"]


class WikiMemberAddIn(BaseModel):
    """``POST /wikis/{id}/members`` — invite an existing user by email
    into a private wiki. Org members of a public wiki don't need a row
    here — they have implicit access from their org membership."""

    email: EmailStr
    role: WikiRole = "editor"


class WikiMemberRoleUpdateIn(BaseModel):
    role: WikiRole


class WikiMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    email: str
    display_name: str | None
    role: WikiRole
    created_at: datetime


class WikiPageCreateIn(BaseModel):
    """``POST /wikis/{id}/pages`` — create a page inside a wiki."""

    title: Annotated[str, Field(max_length=200)] | None = None
    parent_id: uuid.UUID | None = None
    # Markdown source. ``None`` → server uses the default (empty).
    body: Annotated[str, Field(max_length=1_000_000)] | None = None


class WikiPageUpdateIn(BaseModel):
    """``PATCH /wiki-pages/{id}`` — partial update with optimistic
    concurrency via ``revision``."""

    title: Annotated[str, Field(max_length=200)] | None = None
    body: Annotated[str, Field(max_length=1_000_000)] | None = None
    parent_id: uuid.UUID | None = None
    revision: int


class WikiPageListOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    wiki_id: uuid.UUID
    parent_id: uuid.UUID | None
    title: str
    position: int
    revision: int
    created_at: datetime
    updated_at: datetime


class WikiPageDetailOut(WikiPageListOut):
    """Full page payload — markdown body included."""

    body: str
    created_by_user_id: uuid.UUID


class WikiPageMoveIn(BaseModel):
    """``POST /wiki-pages/{id}/move`` — move a page to a different wiki
    and/or re-parent it. At least one field must be set."""

    target_wiki_id: uuid.UUID | None = None
    new_parent_id: uuid.UUID | None = None
