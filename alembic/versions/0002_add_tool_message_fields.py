"""add tool_call_id + tool_calls to messages

Revision ID: 0002_add_tool_message_fields
Revises: 0001_init
Create Date: 2026-05-12

P1.6 / task #7: lets the ReAct loop persist the full trace.
* ``tool_call_id`` references the matching assistant ``tool_calls[i].id``
  for ``role="tool"`` rows.
* ``tool_calls`` is a JSON list on ``role="assistant"`` rows mirroring
  :class:`core.llm.client.ToolCall`.

Both nullable so historical rows survive without backfill.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_tool_message_fields"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine[object]:
    """JSONB on Postgres for index/operator support; JSON elsewhere (SQLite)."""
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("tool_call_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("tool_calls", _json_type(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "tool_calls")
    op.drop_column("messages", "tool_call_id")
