"""AI quality evaluation for assistant messages."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from service.db.base import Base
from service.db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["MessageEvaluation"]

_JSON = JSON().with_variant(postgresql.JSONB(), "postgresql")


class MessageEvaluation(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "message_evaluations"
    __table_args__ = (UniqueConstraint("message_id", name="uq_message_evaluations_message_id"),)

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    overall: Mapped[int] = mapped_column(Integer, nullable=False)
    helpfulness: Mapped[int] = mapped_column(Integer, nullable=False)
    groundedness: Mapped[int] = mapped_column(Integer, nullable=False)
    citation_quality: Mapped[int] = mapped_column(Integer, nullable=False)
    completeness: Mapped[int] = mapped_column(Integer, nullable=False)
    risk: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
