"""add chat_sessions.pinned

Revision ID: 0007_session_pin
Revises: 0006_model_meta
Create Date: 2026-05-13

Lets users pin important conversations to the top of the sidebar. NULL
isn't meaningful here (a session either is pinned or isn't), so the
column is NOT NULL with a ``false`` default so existing rows backfill
cleanly.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_session_pin"
down_revision: str | None = "0006_model_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column(
            "pinned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "pinned")
