"""User-authored metadata for a (provider, model) pair.

Keyed by ``(provider_id, model)`` — provider ownership transitively scopes
to a user, so we don't carry a redundant ``user_id`` column. Deleting a
provider cascades to its metadata rows.

Today this only carries a free-text ``description`` (shown as a tooltip
on hover in the model picker and providers settings page). Future fields
that belong here: per-model temperature defaults, system prompt
overrides, last-used timestamp, etc.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin

__all__ = ["ModelMetadata"]


class ModelMetadata(TimestampMixin, Base):
    __tablename__ = "model_metadata"

    provider_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("providers.id", ondelete="CASCADE"),
        primary_key=True,
    )
    model: Mapped[str] = mapped_column(String(256), primary_key=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
