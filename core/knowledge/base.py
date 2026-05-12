"""Knowledge-base contract + retrieval hit dataclass.

The :class:`KnowledgeBase` Protocol is the integration seam between
:class:`~core.chat_service.ChatService` and a retriever implementation.
Two concrete impls exist today:

* :class:`~core.knowledge.local.FileKnowledgeBase` — on-disk JSONL store
  with stdlib cosine search; used in the unauthenticated CLI path.
* :class:`~core.knowledge.pgvector.PgvectorKnowledgeBase` — production
  retriever over Postgres + pgvector + pg_trgm; used once a DB is
  reachable and the user is logged in.
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


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    """Document-level metadata, shared across all KB impls.

    Both :class:`~core.knowledge.local.FileKnowledgeBase` (on-disk JSONL)
    and :class:`~core.knowledge.pgvector.PgvectorKnowledgeBase` (Postgres
    + pgvector) return this from their ``list_documents`` /
    ``add_document`` admin API so REPL slash commands (``/kb``, ``/save``)
    don't have to branch on KB type for inspection.

    ``id`` is the string form of the underlying identifier — UUID hex on
    both impls today. ``tags`` is preserved through ``meta["tags"]`` on
    Pgvector so the same field round-trips through both stores.
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

    async def search(self, query: str, *, top_k: int = 4) -> list[KnowledgeHit]:
        ...
