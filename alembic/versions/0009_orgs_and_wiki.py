"""add orgs, org_members, wiki_pages + backfill personal orgs

Revision ID: 0009_orgs_and_wiki
Revises: 0008_shares_bookmarks
Create Date: 2026-05-13

Three new tables to support a Notion/Lark-style wiki feature:

* ``orgs`` — workspace namespaces. Every user has exactly one
  ``is_personal=true`` org auto-created on signup (and backfilled
  here for existing users).
* ``org_members`` — composite ``(org_id, user_id)`` PK with a role
  string (``owner``, ``editor``, ``viewer``).
* ``wiki_pages`` — block-based rich documents owned by an org. The
  ``content`` column is the BlockNote block tree serialised as JSON.
  ``revision`` powers optimistic-concurrency autosave.

The backfill step issues one ``INSERT … SELECT`` per table so it scales
with the number of existing users. Slugs use the form
``personal-<first-12-hex-of-uuid>`` which is collision-free by
construction (users.id is a UUID).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_orgs_and_wiki"
down_revision: str | None = "0008_shares_bookmarks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
_JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("owner_id", _UUID, nullable=False),
        sa.Column(
            "is_personal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
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
            ["owner_id"], ["users.id"], ondelete="CASCADE",
            name="fk_orgs_owner_id_users",
        ),
    )
    op.create_index("ix_orgs_slug", "orgs", ["slug"])
    op.create_index("ix_orgs_owner_id", "orgs", ["owner_id"])

    op.create_table(
        "org_members",
        sa.Column("org_id", _UUID, primary_key=True),
        sa.Column("user_id", _UUID, primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], ondelete="CASCADE",
            name="fk_org_members_org_id_orgs",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_org_members_user_id_users",
        ),
    )
    op.create_index("ix_org_members_user_id", "org_members", ["user_id"])

    op.create_table(
        "wiki_pages",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("org_id", _UUID, nullable=False),
        sa.Column("created_by_user_id", _UUID, nullable=False),
        sa.Column("parent_id", _UUID, nullable=True),
        sa.Column(
            "title",
            sa.String(200),
            nullable=False,
            server_default="Untitled",
        ),
        sa.Column(
            "content",
            _JSON,
            nullable=False,
            server_default=sa.text("'[]'::jsonb")
            if op.get_bind().dialect.name == "postgresql"
            else sa.text("'[]'"),
        ),
        sa.Column(
            "position",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            server_default="1",
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
            name="fk_wiki_pages_org_id_orgs",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_wiki_pages_created_by_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["wiki_pages.id"], ondelete="SET NULL",
            name="fk_wiki_pages_parent_id_wiki_pages",
        ),
    )
    op.create_index("ix_wiki_pages_org_id", "wiki_pages", ["org_id"])

    # ── Backfill: one personal org per existing user ─────────────────
    # Run these in plain SQL via op.execute so they target whatever DB
    # is being upgraded. We use ``gen_random_uuid()`` on Postgres; on
    # SQLite (unit-test in-memory schema) the tables are empty so the
    # INSERT … SELECT is a no-op anyway.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            INSERT INTO orgs (id, slug, name, owner_id, is_personal,
                              created_at, updated_at)
            SELECT
                gen_random_uuid(),
                'personal-' || substring(replace(u.id::text, '-', '')
                                         from 1 for 12),
                COALESCE(u.display_name, split_part(u.email, '@', 1))
                  || '''s workspace',
                u.id,
                true,
                NOW(),
                NOW()
            FROM users u
            WHERE NOT EXISTS (
                SELECT 1 FROM orgs o
                WHERE o.owner_id = u.id AND o.is_personal = true
            );
            """
        )
        op.execute(
            """
            INSERT INTO org_members (org_id, user_id, role, created_at)
            SELECT o.id, o.owner_id, 'owner', NOW()
            FROM orgs o
            WHERE o.is_personal = true
              AND NOT EXISTS (
                SELECT 1 FROM org_members m
                WHERE m.org_id = o.id AND m.user_id = o.owner_id
              );
            """
        )


def downgrade() -> None:
    op.drop_index("ix_wiki_pages_org_id", "wiki_pages")
    op.drop_table("wiki_pages")
    op.drop_index("ix_org_members_user_id", "org_members")
    op.drop_table("org_members")
    op.drop_index("ix_orgs_owner_id", "orgs")
    op.drop_index("ix_orgs_slug", "orgs")
    op.drop_table("orgs")
