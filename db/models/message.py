"""Individual turn in a chat session.

Extended in #7 (P1.6) with tool-flavoured columns so the ReAct loop can
persist its full trace:

* ``role="tool"`` rows store tool **results** (``tool_call_id`` references
  the matching assistant turn; ``content`` is what the LLM gets back).
* ``role="assistant"`` rows may carry ``tool_calls`` (JSON list of
  ``{id, name, arguments}``) when the assistant requested calls instead of
  (or alongside) emitting text.

Both new columns are nullable — pre-P1.6 rows continue to load fine.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["VALID_ROLES", "Message"]

# Plain string column so adding new roles requires no schema change; a
# DB-level CHECK constraint may be added later.
VALID_ROLES: frozenset[str] = frozenset({"user", "assistant", "system", "tool"})

# Portable JSON: JSONB on Postgres for index/operator support, plain JSON
# elsewhere (SQLite test harness, etc.).
_JSON = JSON().with_variant(postgresql.JSONB(), "postgresql")


class Message(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional usage accounting (filled in when provider returns token counts).
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ------------------------------------------------------------------
    # Tool-calling fields (#7 P1.6). Both nullable so pre-P1.6 rows still
    # load via the ORM.
    # ------------------------------------------------------------------

    # On ``role="tool"`` rows: references the assistant ``tool_calls[i].id``
    # this row is a result for. Null on every other role.
    tool_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # On ``role="assistant"`` rows: list of {id, name, arguments} dicts mirroring
    # :class:`core.llm.client.ToolCall`. Null when the assistant emitted no
    # tool calls (the common case).
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(
        _JSON,
        nullable=True,
    )
