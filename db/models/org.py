"""Organization model — a namespace that owns wiki pages and (later)
knowledge bases and chat sessions.

Every user has exactly one *personal* org auto-provisioned on signup
(``is_personal=true``); it cannot be deleted. Beyond that they may
create regular orgs and invite teammates.

Membership lives in :class:`db.models.org_member.OrgMember`. ``owner_id``
on this row is denormalised so queries that need "who can manage this
org" don't have to join. It must always match a row in ``org_members``
with role=owner.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["Org"]


class Org(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "orgs"

    # URL-safe identifier. Personal orgs use ``personal-<8 hex>`` so they
    # never collide with user-chosen slugs.
    slug: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # True for the auto-created per-user org. We refuse delete on these
    # rows so users can't accidentally orphan their default workspace.
    is_personal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
