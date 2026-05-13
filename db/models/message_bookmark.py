"""Private bookmark on a single Q&A pair.

Mirrors :class:`db.models.message_share.MessageShare` but without a
public token — bookmarks are listed via ``GET /bookmarks`` after auth.
``note`` is an optional free-text tag the user can attach when saving.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["MessageBookmark"]


class MessageBookmark(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "message_bookmarks"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "assistant_message_id",
            name="uq_message_bookmarks_user_assistant",
        ),
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
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
