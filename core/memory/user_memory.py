"""Long-term per-user memory store + fact-extractor hook (#16 P3.3).

Two roles in one module:

* :class:`UserMemoryStore` — user-bound CRUD over the ``user_memories``
  table. Mirrors :class:`~core.memory.chat_memory.DbChatMemory` in spirit:
  constructed with ``(session_factory, user_id)`` and never crosses user
  boundaries.
* :class:`FactExtractor` Protocol — pluggable hook that turns the just-
  finished conversation turn into a list of new facts to persist. The
  default :class:`NoopFactExtractor` is a no-op so ``ChatService`` can
  always invoke "extract + store" without conditional logic.

Why a Protocol and not a function: a real extractor needs an LLM client and
a tokenizer to do its job, and we want the construction to happen once
(outside the hot path). Passing a stateful object handles that cleanly.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from core.llm.client import ChatMessage

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = [
    "FactExtractor",
    "NoopFactExtractor",
    "UserMemoryEntry",
    "UserMemoryStore",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UserMemoryEntry:
    """A single stored fact, surface-friendly shape."""

    id: uuid.UUID
    content: str
    created_at: datetime
    source_session_id: uuid.UUID | None


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


class UserMemoryStore:
    """User-bound CRUD over the ``user_memories`` table.

    Construct with ``(session_factory, user_id)``. Every method opens a
    short-lived :class:`AsyncSession`; the store instance itself holds no
    cursor / transaction state.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        user_id: uuid.UUID,
    ) -> None:
        self._sf = session_factory
        self._user_id = user_id

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------
    async def add(
        self,
        content: str,
        *,
        source_session_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Store a new fact and return its id.

        Empty / whitespace ``content`` is rejected so the ``/remember``
        command (or a buggy extractor) can't pollute the table with no-op
        rows.
        """
        cleaned = content.strip()
        if not cleaned:
            raise ValueError("user memory content cannot be empty")

        from db.models import UserMemory

        async with self._sf() as s:
            entry = UserMemory(
                user_id=self._user_id,
                content=cleaned,
                source_session_id=source_session_id,
            )
            s.add(entry)
            await s.commit()
            await s.refresh(entry)
            return entry.id

    async def delete(self, memory_id: uuid.UUID) -> None:
        """Drop a fact. No-op if it isn't owned by the bound user (defence
        in depth — routes already check, but a stale id from a previous
        login should silently fail rather than 500)."""
        from db.models import UserMemory

        async with self._sf() as s:
            row = await s.get(UserMemory, memory_id)
            if row is None or row.user_id != self._user_id:
                return
            await s.delete(row)
            await s.commit()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    async def recent(self, limit: int = 10) -> list[UserMemoryEntry]:
        """Return the most recently *created* memories owned by ``user_id``.

        Stamps ``last_accessed_at`` so future cleanup jobs can prune cold
        memories. The bump happens in the same transaction so the read
        and the access-time write share atomicity.
        """
        from sqlalchemy import select, update

        from db.models import UserMemory

        async with self._sf() as s:
            stmt = (
                select(UserMemory)
                .where(UserMemory.user_id == self._user_id)
                .order_by(UserMemory.created_at.desc())
                .limit(limit)
            )
            rows = list((await s.scalars(stmt)).all())
            if rows:
                now = datetime.now(timezone.utc)
                await s.execute(
                    update(UserMemory)
                    .where(UserMemory.id.in_([r.id for r in rows]))
                    .values(last_accessed_at=now)
                )
                await s.commit()
            return [
                UserMemoryEntry(
                    id=r.id,
                    content=r.content,
                    created_at=r.created_at,
                    source_session_id=r.source_session_id,
                )
                for r in rows
            ]


# ---------------------------------------------------------------------------
# Fact extractor (hook for auto-population)
# ---------------------------------------------------------------------------


@runtime_checkable
class FactExtractor(Protocol):
    """Pluggable extractor: ``transcript → list of new facts to remember``.

    Implementations should be **conservative**: it's better to miss a fact
    than to persist a hallucinated one. Returning ``[]`` means "no new
    facts from this turn"; the orchestrator handles that case cleanly.
    """

    async def extract(self, messages: list[ChatMessage]) -> list[str]:
        ...


class NoopFactExtractor:
    """Default extractor — never extracts anything.

    Lets :class:`~core.chat_service.ChatService` always call the hook
    without conditional plumbing. Production deployments swap this for an
    LLM-backed extractor once prompt engineering is tuned.
    """

    async def extract(self, messages: list[ChatMessage]) -> list[str]:
        del messages
        return []
