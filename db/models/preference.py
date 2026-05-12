"""Per-user runtime preferences (one row per user).

``user_id`` is also the primary key — there is at most one preferences row
per user, written lazily on first PUT. The columns all carry "default"
semantics: the value applied when a chat session does not pin its own
provider/model, and the initial state for new chat sessions' RAG toggle.

When ``default_provider_id`` is NULL the API falls back to the user's
first :class:`db.models.provider.Provider` row (or rejects chat requests
if none is configured).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin

__all__ = ["UserPreference"]


class UserPreference(TimestampMixin, Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    default_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("providers.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    default_use_rag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
