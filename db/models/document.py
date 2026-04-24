"""Document (source material for RAG) model.

``meta`` uses ``JSONB`` on Postgres for first-class indexability; on
SQLite we fall back to the generic ``JSON`` type (no-op for us beyond
serialisation — unit tests do not query into meta).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["Document"]


_JSONType = JSONB().with_variant(JSON(), "sqlite")


class Document(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "documents"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(_JSONType, default=dict, nullable=False)
