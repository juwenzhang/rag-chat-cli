"""Org membership.

Composite primary key ``(org_id, user_id)`` — one membership row per
user per org. ``role`` is a free-form short string but only three values
are valid today: ``owner``, ``editor``, ``viewer``. We don't use a
PostgreSQL ENUM so adding roles later is just an app-layer change.

Role semantics (enforced in the router, not the DB):
* ``owner``   — full control: rename/delete the org, manage members,
  read/write all pages.
* ``editor``  — read + write pages, cannot change membership.
* ``viewer``  — read-only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base

__all__ = ["OrgMember"]


class OrgMember(Base):
    __tablename__ = "org_members"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
