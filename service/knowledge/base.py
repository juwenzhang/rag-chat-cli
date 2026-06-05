"""Knowledge-base contract + retrieval hit dataclass.

The :class:`KnowledgeBase` Protocol is the integration seam between
:class:`~service.chat.service.ChatService` and a retriever implementation.
The single production impl is :class:`~service.knowledge.pgvector.PgvectorKnowledgeBase`
(Postgres + pgvector + pg_trgm); all surfaces (REST / SSE / WS / TUI) talk
to the server, so there is no on-disk fallback retriever anymore.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

__all__ = [
    "DocumentInfo",
    "KnowledgeBase",
    "KnowledgeHit",
]


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    """One retrieved knowledge chunk rendered to the UI / returned via API."""

    title: str
    content: str
    score: float
    source: str
    document_id: str | None = None
    chunk_id: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    """Document-level metadata returned by KB admin API.

    ``id`` is the string form of the underlying UUID. ``tags`` round-trips
    via ``meta["tags"]`` on the pgvector backend.
    """

    id: str
    title: str
    source: str
    tags: list[str] = field(default_factory=list)
    chunk_count: int = 0
    char_count: int = 0
    created_at: str = ""


@runtime_checkable
class KnowledgeBase(Protocol):
    """Retriever contract — async to match the rest of ``core/``."""

    async def search(self, query: str, *, top_k: int = 4) -> list[KnowledgeHit]: ...
