"""add sources to messages

Revision ID: 0014_message_sources
Revises: 0013_document_body_column
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014_message_sources"
down_revision: str | None = "0013_document_body_column"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine[object]:
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def upgrade() -> None:
    op.add_column("messages", sa.Column("sources", _json_type(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "sources")
