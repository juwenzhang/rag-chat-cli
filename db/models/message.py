"""Individual turn in a chat session."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["Message"]

# ``role`` is stored as a plain string so new values (e.g. "tool") do not
# require a migration; a DB-level check constraint can be added later.
VALID_ROLES: frozenset[str] = frozenset({"user", "assistant", "system"})


class Message(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional usage accounting (filled in when provider returns token counts).
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
