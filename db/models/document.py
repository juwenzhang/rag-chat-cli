"""Document (source material for RAG) model.

``body`` stores plain markdown text, matching the wiki page model.
The editor round-trips markdown directly; the same renderer + future
RAG ingest pipeline can chunk it without a special-case JSON walk.

``meta`` (JSONB) is kept for backward compat and future extensibility
but content now lives in ``body``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
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
    title: Mapped[str] = mapped_column(
        String(256), nullable=False, server_default="Untitled"
    )
    body: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=""
    )
    meta: Mapped[dict[str, Any]] = mapped_column(_JSONType, default=dict, nullable=False)
