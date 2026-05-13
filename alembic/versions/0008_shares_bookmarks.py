"""add message_shares and message_bookmarks

Revision ID: 0008_shares_bookmarks
Revises: 0007_session_pin
Create Date: 2026-05-13

Two new tables to support per-Q&A sharing and bookmarking:

* ``message_shares`` — public, token-addressable. CASCADE deletes when
  the source session/message disappears (we picked **live links** over
  snapshot — see the design conversation).
* ``message_bookmarks`` — private to the user.

Both enforce ``UNIQUE(user_id, assistant_message_id)`` so each Q&A pair
can have at most one active share / bookmark per user; re-doing the
action is a get-or-create.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008_shares_bookmarks"
down_revision: str | None = "0007_session_pin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "message_shares",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("token", sa.String(24), nullable=False, unique=True),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("session_id", _UUID, nullable=False),
        sa.Column("user_message_id", _UUID, nullable=False),
        sa.Column("assistant_message_id", _UUID, nullable=False),
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
            name="fk_message_shares_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["chat_sessions.id"], ondelete="CASCADE",
            name="fk_message_shares_session_id_chat_sessions",
        ),
        sa.ForeignKeyConstraint(
            ["user_message_id"], ["messages.id"], ondelete="CASCADE",
            name="fk_message_shares_user_message_id_messages",
        ),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"], ["messages.id"], ondelete="CASCADE",
            name="fk_message_shares_assistant_message_id_messages",
        ),
        sa.UniqueConstraint(
            "user_id", "assistant_message_id",
            name="uq_message_shares_user_assistant",
        ),
    )
    op.create_index(
        "ix_message_shares_user_id", "message_shares", ["user_id"],
    )

    op.create_table(
        "message_bookmarks",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("session_id", _UUID, nullable=False),
        sa.Column("user_message_id", _UUID, nullable=False),
        sa.Column("assistant_message_id", _UUID, nullable=False),
        sa.Column("note", sa.String(512), nullable=True),
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
            name="fk_message_bookmarks_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["chat_sessions.id"], ondelete="CASCADE",
            name="fk_message_bookmarks_session_id_chat_sessions",
        ),
        sa.ForeignKeyConstraint(
            ["user_message_id"], ["messages.id"], ondelete="CASCADE",
            name="fk_message_bookmarks_user_message_id_messages",
        ),
        sa.ForeignKeyConstraint(
            ["assistant_message_id"], ["messages.id"], ondelete="CASCADE",
            name="fk_message_bookmarks_assistant_message_id_messages",
        ),
        sa.UniqueConstraint(
            "user_id", "assistant_message_id",
            name="uq_message_bookmarks_user_assistant",
        ),
    )
    op.create_index(
        "ix_message_bookmarks_user_id", "message_bookmarks", ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_bookmarks_user_id", "message_bookmarks")
    op.drop_table("message_bookmarks")
    op.drop_index("ix_message_shares_user_id", "message_shares")
    op.drop_table("message_shares")
