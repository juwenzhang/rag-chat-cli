"""Per-wiki membership — only meaningful for ``visibility="private"`` wikis.

For an ``org_wide`` wiki we ignore this table entirely; access derives
from the user's org membership. For a ``private`` wiki, the explicit
rows here are the *only* path in (plus the org owner — they always
have admin rights to anything in their workspace).

Roles mirror :class:`db.models.org_member.OrgMember`'s role enum:
``editor`` or ``viewer``. We deliberately don't allow ``owner`` at the
wiki level — wiki ownership is the org's job.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base

__all__ = ["WikiMember"]


class WikiMember(Base):
    __tablename__ = "wiki_members"

    wiki_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("wikis.id", ondelete="CASCADE"),
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
