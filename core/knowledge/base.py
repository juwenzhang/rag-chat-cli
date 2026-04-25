"""Knowledge-base abstractions.

This module intentionally stops at the minimum surface needed by
:class:`core.chat_service.ChatService` in P2: a :class:`KnowledgeBase`
protocol plus a :class:`FileKnowledgeBase` placeholder that always returns
no hits. A real retriever lands in change
``implement-rag-retrieval-pgvector`` (P7).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "KnowledgeHit",
    "KnowledgeBase",
    "FileKnowledgeBase",
]


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    """One retrieved knowledge chunk rendered to the UI / returned via API."""

    title: str
    content: str
    score: float
    source: str


@runtime_checkable
class KnowledgeBase(Protocol):
    """Retriever contract — async to match the rest of ``core/``."""

    async def search(
        self, query: str, *, top_k: int = 4
    ) -> list[KnowledgeHit]:
        ...


class FileKnowledgeBase:
    """Placeholder implementation returning no hits.

    Kept as a valid :class:`KnowledgeBase` so :class:`ChatService` can run
    end-to-end with ``use_rag=True`` even before real retrieval exists.
    The real implementation (``PgvectorKnowledgeBase``) will replace this
    one in change ``implement-rag-retrieval-pgvector``.
    """

    def __init__(
        self,
        root: str | Path = "./knowledge",
        *,
        min_score: float = 0.0,
    ) -> None:
        self._root = Path(root)
        self._min_score = min_score

    @classmethod
    def from_settings(cls, s: Any | None = None) -> "FileKnowledgeBase":
        if s is None:
            from settings import settings as _s

            s = _s
        return cls(min_score=float(s.retrieval.min_score))

    async def search(
        self, query: str, *, top_k: int = 4
    ) -> list[KnowledgeHit]:
        del query, top_k  # no-op until P7 implements real retrieval

        async def _noop() -> list[KnowledgeHit]:
            return []

        return await asyncio.shield(_noop())


# class PgvectorKnowledgeBase:  # noqa: ERA001 — placeholder for P7
#     """Will be implemented in ``implement-rag-retrieval-pgvector``."""
