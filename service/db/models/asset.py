"""Uploaded user assets such as images."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from service.db.base import Base
from service.db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["Asset"]


class Asset(UUIDMixin, TimestampMixin, Base):
    __tablename__: str = "assets"
    __table_args__: tuple[Index, Index] = (
        Index("ix_assets_user_id_source_hash", "user_id", "source_hash", unique=True),
        Index("ix_assets_user_id_content_hash", "user_id", "content_hash", unique=True),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
