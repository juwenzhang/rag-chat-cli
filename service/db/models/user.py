"""User account model (AGENTS.md §14).

P-AUTH-2 (multi-provider login): ``hashed_password`` is now optional —
authoritative credentials live in :class:`service.db.models.UserIdentity`.
The column is kept around (nullable) for one release cycle so a service
rollback can still authenticate password users from the old source. New
writes must go through ``UserIdentity`` — the AuthService treats this
column as read-only.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from service.db.base import Base
from service.db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["User"]


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Deprecated read-only fallback. See module docstring + alembic 0018.
    # Code paths post P-AUTH-2 read/write credentials via ``user_identities``.
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
