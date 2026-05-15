"""Per-wiki-page public share link.

A row maps a short URL-safe ``token`` to a specific wiki page. The share
is rendered **live** — we look up the page at view time rather than
snapshotting content, so CASCADE on the page FK is intentional: deleting
the page also kills the share.

``UNIQUE(user_id, page_id)`` makes ``POST /wiki-page-shares`` a
get-or-create: re-sharing the same page reuses the existing token.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["WikiPageShare"]


class WikiPageShare(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "wiki_page_shares"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "page_id",
            name="uq_wiki_page_shares_user_page",
        ),
    )

    token: Mapped[str] = mapped_column(
        String(24), unique=True, nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wiki_pages.id", ondelete="CASCADE"),
        nullable=False,
    )
