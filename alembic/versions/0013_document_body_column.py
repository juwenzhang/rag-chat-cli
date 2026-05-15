"""add body column to documents, migrate meta.content

Revision ID: 0013_document_body_column
Revises: 0012_wiki_page_shares
Create Date: 2026-05-15

Adds a dedicated ``body`` Text column to ``documents`` (matching the
wiki_pages model) and migrates existing content from ``meta->>'content'``
into it. Also makes ``title`` NOT NULL with a default of 'Untitled'.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_document_body_column"
down_revision: str | None = "0012_wiki_page_shares"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add body column (nullable initially for the data migration).
    op.add_column(
        "documents",
        sa.Column("body", sa.Text(), server_default="", nullable=True),
    )

    # 2. Migrate existing meta.content → body.
    #    Postgres: meta->>'content'
    #    SQLite:   json_extract(meta, '$.content')
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute(
            sa.text(
                "UPDATE documents SET body = COALESCE(meta->>'content', '') "
                "WHERE body IS NULL OR body = ''"
            )
        )
    else:
        op.execute(
            sa.text(
                "UPDATE documents SET body = COALESCE(json_extract(meta, '$.content'), '') "
                "WHERE body IS NULL OR body = ''"
            )
        )

    # 3. Make body NOT NULL.
    op.alter_column(
        "documents", "body",
        existing_type=sa.Text(),
        nullable=False,
        server_default="",
    )

    # 4. Fix title: fill NULLs, then make NOT NULL.
    op.execute(
        sa.text("UPDATE documents SET title = 'Untitled' WHERE title IS NULL")
    )
    op.alter_column(
        "documents", "title",
        existing_type=sa.String(256),
        nullable=False,
        server_default="Untitled",
    )


def downgrade() -> None:
    # Revert title back to nullable.
    op.alter_column(
        "documents", "title",
        existing_type=sa.String(256),
        nullable=True,
        server_default=None,
    )
    # Drop body column.
    op.drop_column("documents", "body")
