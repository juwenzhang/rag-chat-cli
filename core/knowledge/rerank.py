"""Reranker hook for the retrieval pipeline (#13 P2.5).

The Protocol exists so :class:`~core.knowledge.pgvector.PgvectorKnowledgeBase`
can defer the "narrow N candidates down to top-K" decision to a strategy
object — without taking a dependency on any specific reranker library.

The default implementation is :class:`NoopReranker`, which sorts by score
and truncates. Production deployments can swap in a cross-encoder
(``bge-reranker-v2-m3``, Cohere Rerank, etc.) by writing a class that
satisfies the Protocol and passing it to ``PgvectorKnowledgeBase``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.knowledge.base import KnowledgeHit

__all__ = ["NoopReranker", "Reranker"]


@runtime_checkable
class Reranker(Protocol):
    """Rerank candidates by relevance to ``query``, returning at most ``top_k``."""

    async def rerank(
        self,
        query: str,
        hits: list[KnowledgeHit],
        *,
        top_k: int = 4,
    ) -> list[KnowledgeHit]:
        ...


class NoopReranker:
    """Default reranker: sort by existing ``score`` descending, truncate to ``top_k``.

    Useful as a hook point (so callers always invoke a reranker) and as a
    sane default before a real cross-encoder is wired up. The ``score``
    fields are left untouched — a real reranker is expected to overwrite
    them with its own relevance scores.
    """

    async def rerank(
        self,
        query: str,
        hits: list[KnowledgeHit],
        *,
        top_k: int = 4,
    ) -> list[KnowledgeHit]:
        del query  # the noop reranker ignores the query
        ordered = sorted(hits, key=lambda h: h.score, reverse=True)
        return ordered[:top_k]
