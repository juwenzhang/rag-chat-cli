"""Chat DTOs (AGENTS.md §5 / §14)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ChatSessionOut",
    "ChatSessionUpdateIn",
    "CreateSessionIn",
    "MessageIn",
    "MessageOut",
]


class CreateSessionIn(BaseModel):
    """Request body for ``POST /chat/sessions``."""

    title: Annotated[str, Field(max_length=256)] | None = None
    # Optional per-session provider/model pin (Sprint 2). NULL inherits
    # the user's preference defaults.
    provider_id: uuid.UUID | None = None
    model: Annotated[str, Field(max_length=128)] | None = None


class ChatSessionUpdateIn(BaseModel):
    """Request body for ``PATCH /chat/sessions/{id}``.

    All fields optional — ``None`` means "don't touch". The ``clear_*``
    sentinels let callers wipe the pin without confusing it with "not
    sent".
    """

    title: Annotated[str, Field(max_length=256)] | None = None
    provider_id: uuid.UUID | None = None
    model: Annotated[str, Field(max_length=128)] | None = None
    clear_provider_id: bool = False
    clear_model: bool = False


class ChatSessionOut(BaseModel):
    """Response projection for a chat session row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    provider_id: uuid.UUID | None = None
    model: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageIn(BaseModel):
    """Request body for ``POST /chat/messages`` (non-streaming)."""

    session_id: uuid.UUID
    content: Annotated[str, Field(min_length=1, max_length=32_000)]
    use_rag: bool = False


class MessageOut(BaseModel):
    """Response projection for a stored message row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: Literal["user", "assistant", "system"]
    content: str
    tokens: int | None = None
    created_at: datetime
