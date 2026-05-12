"""add user_memories table (#16 P3.3)

Revision ID: 0003_add_user_memories
Revises: 0002_add_tool_message_fields
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_user_memories"
down_revision: str | None = "0002_add_tool_message_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Match the helper used elsewhere — PG UUID falls back to String(36) on SQLite.
_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "user_memories",
        sa.Column("id", _UUID, primary_key=True),
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
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_session_id", _UUID, nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_user_memories_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["source_session_id"],
            ["chat_sessions.id"],
            ondelete="SET NULL",
            name="fk_user_memories_source_session_id_chat_sessions",
        ),
    )
    op.create_index("ix_user_memories_user_id", "user_memories", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_memories_user_id", table_name="user_memories")
    op.drop_table("user_memories")
