"""Wiki (knowledge base) — a named collection of wiki pages within an org.

Hierarchy::

    User → Workspace (Org) → Wiki → Page

Every org auto-provisions a default wiki on creation (and the
migration backfills one per existing org) so users with a personal
workspace always have a place to write without ever having to think
about wikis. Power users can create additional wikis with different
visibility / member sets.

Permission resolution:

* ``visibility == "org_wide"`` (default): any org member can read; org
  editor/owner can write.
* ``visibility == "private"``: only rows in
  :class:`db.models.wiki_member.WikiMember` (plus the org owner) can
  access. Pages inherit the wiki's visibility.

The RAG layer (not landed yet) will scope retrieval by wiki_id, so
private wikis stay invisible to AI sessions that don't have access.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["Wiki"]


class Wiki(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "wikis"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_wikis_org_id_slug"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # True for the auto-created wiki of each org. We refuse delete on
    # the default wiki so users can't accidentally orphan their pages.
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    # ``org_wide`` (default) or ``private``. App-layer enum — no DB
    # enum so future values can land without a migration.
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="org_wide", default="org_wide"
    )
