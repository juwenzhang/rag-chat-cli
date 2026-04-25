"""Chat DTOs (AGENTS.md §5 / §14)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ChatSessionOut",
    "CreateSessionIn",
    "MessageIn",
    "MessageOut",
]


class CreateSessionIn(BaseModel):
    """Request body for ``POST /chat/sessions``."""

    title: Annotated[str, Field(max_length=256)] | None = None


class ChatSessionOut(BaseModel):
    """Response projection for a chat session row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
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
