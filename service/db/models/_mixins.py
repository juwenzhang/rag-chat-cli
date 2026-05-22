"""Shared ORM mixins.

* :class:`UUIDMixin` — UUID-as-primary-key that renders as ``UUID`` on
  Postgres and ``String(36)`` on SQLite, so the unit test harness can
  build the schema on an in-memory database.
* :class:`TimestampMixin` — ``created_at`` / ``updated_at`` columns
  populated by the server (``NOW()``) on insert and update.

Both mixins are declarative-friendly — they use ``mapped_column`` so
:class:`db.base.Base` sub-classes can just inherit them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, TypeDecorator, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

__all__ = ["TimestampMixin", "UUIDMixin"]


class _UUID(TypeDecorator[uuid.UUID]):
    """UUID column that works on Postgres (native ``UUID``) and SQLite
    (``CHAR(36)`` string). Python-side values are always :class:`uuid.UUID`.
    """

    impl = String
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(
        self, value: uuid.UUID | str | None, dialect: Any
    ) -> uuid.UUID | str | None:
        if value is None:
            return None
        if dialect.name == "postgresql":
            # asyncpg / psycopg handle uuid.UUID natively.
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value) if isinstance(value, uuid.UUID) else value

    def process_result_value(self, value: str | uuid.UUID | None, dialect: Any) -> uuid.UUID | None:
        if value is None:
            return None
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


class UUIDMixin:
    """Adds a UUID primary key auto-populated via ``uuid.uuid4()``."""

    id: Mapped[uuid.UUID] = mapped_column(
        _UUID(),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Adds ``created_at`` / ``updated_at`` server-side timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
