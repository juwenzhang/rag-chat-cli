"""Per-Q&A public share link.

A row maps a short URL-safe ``token`` to a specific (user message,
assistant message) pair inside a chat session. The share is rendered
**live** — we look up the messages at view time rather than snapshotting
content, so CASCADE on the source FKs is intentional: deleting the
session or messages also kills the share.

The ``UNIQUE(user_id, assistant_message_id)`` constraint means
``POST /shares`` is a get-or-create: re-sharing the same Q&A reuses the
existing token instead of generating a new one.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["MessageShare"]


class MessageShare(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "message_shares"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "assistant_message_id",
            name="uq_message_shares_user_assistant",
        ),
    )

    token: Mapped[str] = mapped_column(
        String(24), unique=True, nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    assistant_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )
