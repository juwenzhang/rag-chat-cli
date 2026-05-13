"""DTOs for ``/shares`` and ``/bookmarks`` (per-Q&A sharing + favourites)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "BookmarkCreateIn",
    "BookmarkOut",
    "ForkFromShareIn",
    "ShareCreateIn",
    "ShareOut",
    "SharePublicOut",
    "SharedMessageOut",
]


class ShareCreateIn(BaseModel):
    """``POST /shares`` body — pin a single Q&A pair."""

    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID


class ShareOut(BaseModel):
    """The owner's view of a share row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    token: str
    session_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    created_at: datetime


class SharedMessageOut(BaseModel):
    """A single rendered message inside a public share payload."""

    role: Literal["user", "assistant"]
    content: str
    tokens: int | None = None
    model: str | None = None
    provider_name: str | None = None
    created_at: datetime


class SharePublicOut(BaseModel):
    """``GET /shares/{token}`` payload — readable by anyone."""

    token: str
    created_at: datetime
    session_id: uuid.UUID
    # ``session_owner_id`` lets the unauthenticated front-end decide whether
    # to render *Continue here* (owner) or *Fork* / *Sign in* (everyone else).
    session_owner_id: uuid.UUID
    user_message: SharedMessageOut
    assistant_message: SharedMessageOut


class BookmarkCreateIn(BaseModel):
    """``POST /bookmarks`` body."""

    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    note: Annotated[str, Field(max_length=512)] | None = None


class BookmarkOut(BaseModel):
    """Owner-only view of a bookmark row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    note: str | None
    created_at: datetime


class ForkFromShareIn(BaseModel):
    """``POST /chat/sessions/from-share`` — clone a Q&A into a new session."""

    token: Annotated[str, Field(min_length=1, max_length=24)]
