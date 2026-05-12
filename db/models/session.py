"""Chat session model — table name ``chat_sessions`` to avoid clashing
with the SQLAlchemy ``Session`` concept.

A row represents one logical conversation (one sidebar item in the
future Web UI). Individual turns live in :class:`db.models.message.Message`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["ChatSession"]


class ChatSession(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    # Per-session provider/model pin (Sprint 2). NULL → fall back to the
    # user's preference, then to the user's default provider.
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True,
    )
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
