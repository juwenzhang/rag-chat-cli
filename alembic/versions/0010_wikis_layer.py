"""introduce wikis layer between orgs and wiki_pages

Revision ID: 0010_wikis_layer
Revises: 0009_orgs_and_wiki
Create Date: 2026-05-13

Refactors the hierarchy from::

    Org → Page

to::

    Org → Wiki → Page

so a workspace can house multiple independently-permissioned knowledge
bases (matches the feishu/yuque mental model the user expects).

Two new tables:

* ``wikis`` — named collection of pages. ``is_default=true`` per org.
* ``wiki_members`` — explicit access entries for private wikis.

``wiki_pages`` swaps its ``org_id`` FK for a ``wiki_id`` FK. The
backfill creates one ``Default`` wiki per existing org and points
every pre-existing page at it, preserving content and ordering.

The migration is forward-only safe: ``downgrade`` reverts by collapsing
all pages back to their wiki's org and dropping the new tables. Pages
that lived in a non-default wiki at downgrade time would all end up in
the same org bucket — acceptable since downgrade is a recovery path,
not a normal flow.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0010_wikis_layer"
down_revision: str | None = "0009_orgs_and_wiki"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    # ── 1. New tables ─────────────────────────────────────────────
    op.create_table(
        "wikis",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("org_id", _UUID, nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("created_by_user_id", _UUID, nullable=False),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "visibility",
            sa.String(16),
            nullable=False,
            server_default="org_wide",
        ),
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
            ["org_id"], ["orgs.id"], ondelete="CASCADE",
            name="fk_wikis_org_id_orgs",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_wikis_created_by_user_id_users",
        ),
        sa.UniqueConstraint("org_id", "slug", name="uq_wikis_org_id_slug"),
    )
    op.create_index("ix_wikis_org_id", "wikis", ["org_id"])

    op.create_table(
        "wiki_members",
        sa.Column("wiki_id", _UUID, primary_key=True),
        sa.Column("user_id", _UUID, primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["wiki_id"], ["wikis.id"], ondelete="CASCADE",
            name="fk_wiki_members_wiki_id_wikis",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_wiki_members_user_id_users",
        ),
    )
    op.create_index(
        "ix_wiki_members_user_id", "wiki_members", ["user_id"]
    )

    # ── 2. Backfill — one default wiki per existing org ───────────
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            INSERT INTO wikis (id, org_id, slug, name, description,
                               created_by_user_id, is_default, visibility,
                               created_at, updated_at)
            SELECT
                gen_random_uuid(),
                o.id,
                'default',
                'Default wiki',
                'Auto-created default knowledge base for this workspace.',
                o.owner_id,
                true,
                'org_wide',
                NOW(),
                NOW()
            FROM orgs o
            WHERE NOT EXISTS (
                SELECT 1 FROM wikis w
                WHERE w.org_id = o.id AND w.is_default = true
            );
            """
        )

    # ── 3. Add wiki_id column to wiki_pages (nullable first) ──────
    op.add_column(
        "wiki_pages",
        sa.Column("wiki_id", _UUID, nullable=True),
    )

    # ── 4. Backfill wiki_pages.wiki_id from wiki_pages.org_id ─────
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            UPDATE wiki_pages p
            SET wiki_id = w.id
            FROM wikis w
            WHERE w.org_id = p.org_id
              AND w.is_default = true
              AND p.wiki_id IS NULL;
            """
        )

    # ── 5. Lock down the new column + index + FK; drop the old one ─
    op.alter_column("wiki_pages", "wiki_id", nullable=False)
    op.create_foreign_key(
        "fk_wiki_pages_wiki_id_wikis",
        "wiki_pages", "wikis",
        ["wiki_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_wiki_pages_wiki_id", "wiki_pages", ["wiki_id"])

    op.drop_index("ix_wiki_pages_org_id", "wiki_pages")
    op.drop_constraint(
        "fk_wiki_pages_org_id_orgs", "wiki_pages", type_="foreignkey"
    )
    op.drop_column("wiki_pages", "org_id")


def downgrade() -> None:
    # Re-introduce org_id, derive it from the wiki's org, then drop the
    # new tables. Pages from non-default wikis end up in the same org
    # bucket as before — fine for a recovery path.
    bind = op.get_bind()
    op.add_column(
        "wiki_pages",
        sa.Column("org_id", _UUID, nullable=True),
    )
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            UPDATE wiki_pages p
            SET org_id = w.org_id
            FROM wikis w
            WHERE w.id = p.wiki_id;
            """
        )
    op.alter_column("wiki_pages", "org_id", nullable=False)
    op.create_foreign_key(
        "fk_wiki_pages_org_id_orgs",
        "wiki_pages", "orgs",
        ["org_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_wiki_pages_org_id", "wiki_pages", ["org_id"])

    op.drop_index("ix_wiki_pages_wiki_id", "wiki_pages")
    op.drop_constraint(
        "fk_wiki_pages_wiki_id_wikis", "wiki_pages", type_="foreignkey"
    )
    op.drop_column("wiki_pages", "wiki_id")

    op.drop_index("ix_wiki_members_user_id", "wiki_members")
    op.drop_table("wiki_members")
    op.drop_index("ix_wikis_org_id", "wikis")
    op.drop_table("wikis")
