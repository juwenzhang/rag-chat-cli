"""Long-term per-user memory facts (#16 P3.3).

One row = one fact ("the user prefers Python over JavaScript", "the user's
team uses Postgres 15"). These are surfaced to every future conversation
for that user via :class:`core.memory.user_memory.UserMemoryStore`, so they
act as a lightweight personalisation layer on top of per-session chat
history.

Schema kept deliberately small:

* ``user_id`` — owner.
* ``content`` — free-text fact.
* ``source_session_id`` — optional pointer back to the conversation the
  fact was extracted from (nullable; manual ``/remember`` entries have no
  source).
* ``last_accessed_at`` — bumped each time the fact is surfaced; lets a
  future cleanup job drop stale memories.

A future iteration can add an ``embedding vector(dim)`` column to enable
semantic retrieval; for the first cut the store ranks by recency only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["UserMemory"]


class UserMemory(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "user_memories"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
