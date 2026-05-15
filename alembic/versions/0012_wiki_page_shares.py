"""add wiki_page_shares

Revision ID: 0012_wiki_page_shares
Revises: 0011_wiki_body_markdown
Create Date: 2026-05-15

Public share links for wiki pages. One row per (user, page) pair via a
UNIQUE constraint; ``POST`` is get-or-create. The share is a live link
— CASCADE on ``page_id`` keeps cleanup automatic.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012_wiki_page_shares"
down_revision: str | None = "0011_wiki_body_markdown"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "wiki_page_shares",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("token", sa.String(24), nullable=False, unique=True),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("page_id", _UUID, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_wiki_page_shares_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"], ["wiki_pages.id"], ondelete="CASCADE",
            name="fk_wiki_page_shares_page_id_wiki_pages",
        ),
        sa.UniqueConstraint(
            "user_id", "page_id",
            name="uq_wiki_page_shares_user_page",
        ),
    )
    op.create_index(
        "ix_wiki_page_shares_user_id", "wiki_page_shares", ["user_id"],
    )
    op.create_index(
        "ix_wiki_page_shares_token", "wiki_page_shares", ["token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_wiki_page_shares_token", "wiki_page_shares")
    op.drop_index("ix_wiki_page_shares_user_id", "wiki_page_shares")
    op.drop_table("wiki_page_shares")
