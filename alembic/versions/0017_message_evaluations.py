"""add message evaluations

Revision ID: 0017_message_evaluations
Revises: 0016_asset_hashes
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017_message_evaluations"
down_revision: str | None = "0016_asset_hashes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = sa.UUID().with_variant(sa.String(36), "sqlite")
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "message_evaluations",
        sa.Column(
            "message_id", _UUID, sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "session_id",
            _UUID,
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", _UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("overall", sa.Integer(), nullable=False),
        sa.Column("helpfulness", sa.Integer(), nullable=False),
        sa.Column("groundedness", sa.Integer(), nullable=False),
        sa.Column("citation_quality", sa.Integer(), nullable=False),
        sa.Column("completeness", sa.Integer(), nullable=False),
        sa.Column("risk", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("raw", _JSON, nullable=True),
        sa.Column("id", _UUID, primary_key=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("message_id", name="uq_message_evaluations_message_id"),
    )
    op.create_index("ix_message_evaluations_message_id", "message_evaluations", ["message_id"])
    op.create_index("ix_message_evaluations_session_id", "message_evaluations", ["session_id"])
    op.create_index("ix_message_evaluations_user_id", "message_evaluations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_message_evaluations_user_id", table_name="message_evaluations")
    op.drop_index("ix_message_evaluations_session_id", table_name="message_evaluations")
    op.drop_index("ix_message_evaluations_message_id", table_name="message_evaluations")
    op.drop_table("message_evaluations")
