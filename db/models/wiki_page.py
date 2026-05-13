"""Wiki page model — a markdown document owned by a :class:`Wiki`.

Storage: the page body is plain markdown text. The editor (Milkdown,
Typora-style WYSIWYG) round-trips markdown directly, so we don't need
a per-block schema or JSONB column. Same data shape as chat messages,
which means the same renderer + future RAG ingest pipeline can chunk
it without a special-case JSON walk.

``parent_id`` is reserved for nested page trees (the sidebar exposes
this); ``revision`` powers optimistic-concurrency autosave: the client
echoes back the revision it last saw, and we 409 on mismatch.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["WikiPage"]


class WikiPage(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "wiki_pages"

    # Pages belong to a :class:`db.models.wiki.Wiki` (which belongs to
    # an org). Migration 0010 introduced this column; 0011 swapped the
    # block JSON for a markdown body.
    wiki_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wikis.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("wiki_pages.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, server_default="Untitled"
    )
    # Markdown source. An empty page starts at ``""`` so the column
    # stays NOT NULL with a sensible default.
    body: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=""
    )
    position: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1", default=1
    )
