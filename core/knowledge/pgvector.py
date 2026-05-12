"""Pgvector-backed retriever with optional hybrid retrieval + rerank hook.

Implements :class:`core.knowledge.base.KnowledgeBase` against the ``chunks``
table created by Alembic 0001 (column ``embedding vector(dim)`` with an
``ivfflat`` cosine index, plus the ``pg_trgm`` extension for trigram
lexical search).

Pipeline (#13 P2.5):

  vector search (top-N)  ──┐
                           ├── RRF fusion ── reranker.rerank() ── top_k
  lexical search (top-N) ──┘                  (NoopReranker by default)

Lexical search uses pg_trgm's similarity operator and falls back to an
empty list on non-Postgres dialects (SQLite test harness), in which case
the pipeline degenerates to "vector-only + reranker truncation".

Two construction modes:

* **User-scoped** — pass a ``user_id``; the search returns documents owned
  by that user plus shared documents (``documents.user_id IS NULL``).
* **Shared-only** — leave ``user_id=None``; returns shared documents only.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from core.knowledge.base import DocumentInfo, KnowledgeHit
from core.knowledge.rerank import NoopReranker, Reranker
from core.llm.client import LLMClient, LLMError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ["PgvectorKnowledgeBase"]

# How many candidates each branch retrieves before fusion. The reranker
# narrows the union back down to ``top_k``. A modest 3× over-fetch is enough
# headroom for fusion to find lexical matches that vector missed (and vice
# versa) without blowing query latency.
CANDIDATE_OVER_FETCH = 3


class PgvectorKnowledgeBase:
    """Cosine-similarity + trigram lexical retriever with rerank hook.

    Construct via :meth:`from_settings` or directly. Holds an
    :class:`async_sessionmaker` (so every search opens its own transaction)
    plus the :class:`LLMClient` used to embed the query and an optional
    :class:`Reranker`.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        llm: LLMClient,
        user_id: uuid.UUID | None = None,
        embed_model: str | None = None,
        min_score: float = 0.0,
        reranker: Reranker | None = None,
        enable_lexical: bool = True,
    ) -> None:
        self._sf = session_factory
        self._llm = llm
        self._user_id = user_id
        self._embed_model = embed_model
        self._min_score = min_score
        self._reranker: Reranker = reranker or NoopReranker()
        self._enable_lexical = enable_lexical

    @classmethod
    def from_settings(
        cls,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        llm: LLMClient,
        user_id: uuid.UUID | None = None,
        reranker: Reranker | None = None,
        s: Any | None = None,
    ) -> PgvectorKnowledgeBase:
        if s is None:
            from settings import settings as _s

            s = _s
        return cls(
            session_factory=session_factory,
            llm=llm,
            user_id=user_id,
            embed_model=s.ollama.embed_model,
            min_score=float(s.retrieval.min_score),
            reranker=reranker,
        )

    # ------------------------------------------------------------------
    # KnowledgeBase
    # ------------------------------------------------------------------
    async def search(self, query: str, *, top_k: int = 4) -> list[KnowledgeHit]:
        """Hybrid retrieval + rerank → at most ``top_k`` hits.

        Empty/whitespace queries short-circuit to ``[]`` without paying for
        an embedding round-trip. Embedding failures surface as
        :class:`core.llm.client.LLMError` — callers (``ChatService``) catch
        these and emit a ``retrieval_failed`` error event.
        """
        if not query or not query.strip():
            return []

        over_fetch = max(top_k * CANDIDATE_OVER_FETCH, top_k)

        # Embed (single query — Ollama embeds one prompt at a time).
        vectors = await self._llm.embed([query], model=self._embed_model)
        if not vectors or not vectors[0]:
            raise LLMError("embedding model returned no vector for query")
        query_vec = vectors[0]

        async with self._sf() as s:
            vector_hits = await self._vector_search(s, query_vec, over_fetch)
            lexical_hits: list[KnowledgeHit] = []
            if self._enable_lexical and _is_postgres(s):
                lexical_hits = await self._lexical_search(s, query, over_fetch)

        fused = _reciprocal_rank_fusion(vector_hits, lexical_hits)
        reranked = await self._reranker.rerank(query, fused, top_k=top_k)
        # Apply min_score threshold AFTER rerank: a real reranker may
        # overwrite scores, so thresholding has to come last.
        return [h for h in reranked if h.score >= self._min_score]

    # ------------------------------------------------------------------
    # Branches
    # ------------------------------------------------------------------
    async def _vector_search(
        self,
        s: AsyncSession,
        query_vec: list[float],
        limit: int,
    ) -> list[KnowledgeHit]:
        from sqlalchemy import or_, select

        from db.models import Chunk, Document

        distance = Chunk.embedding.cosine_distance(query_vec).label("distance")

        if self._user_id is not None:
            ownership = or_(Document.user_id == self._user_id, Document.user_id.is_(None))
        else:
            ownership = Document.user_id.is_(None)

        stmt = (
            select(
                Chunk.id,
                Chunk.content,
                Document.title,
                Document.source,
                distance,
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(ownership)
            .order_by(distance)
            .limit(limit)
        )
        rows = (await s.execute(stmt)).all()
        return [
            KnowledgeHit(
                title=row.title or "(untitled)",
                content=row.content,
                score=1.0 - float(row.distance),
                source=row.source,
            )
            for row in rows
        ]

    async def _lexical_search(
        self,
        s: AsyncSession,
        query: str,
        limit: int,
    ) -> list[KnowledgeHit]:
        """pg_trgm similarity match. Returns ``[]`` on non-Postgres dialects.

        Uses ``similarity(content, :q)`` rather than ``%`` so we can both
        order and score in a single pass. No GIN index yet — on large
        corpora this will need ``CREATE INDEX … USING gin (content gin_trgm_ops)``
        in a follow-up migration. For the first hybrid pass we accept the
        seq-scan cost and let the over-fetch ``limit`` cap latency.
        """
        from sqlalchemy import func, or_, select, text

        from db.models import Chunk, Document

        score_col = func.similarity(Chunk.content, query).label("sim")

        if self._user_id is not None:
            ownership = or_(Document.user_id == self._user_id, Document.user_id.is_(None))
        else:
            ownership = Document.user_id.is_(None)

        stmt = (
            select(
                Chunk.id,
                Chunk.content,
                Document.title,
                Document.source,
                score_col,
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(ownership, text("similarity(chunks.content, :q) > 0").bindparams(q=query))
            .order_by(score_col.desc())
            .limit(limit)
        )
        rows = (await s.execute(stmt)).all()
        return [
            KnowledgeHit(
                title=row.title or "(untitled)",
                content=row.content,
                score=float(row.sim),
                source=row.source,
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Admin / curation API — mirrors :class:`FileKnowledgeBase` so REPL
    # slash commands (`/kb`, `/save`, `/reflect`) work in logged-in mode.
    #
    # ``tags`` round-trip through ``Document.meta['tags']`` since the
    # documents table doesn't have a dedicated column for them. The
    # alembic schema is unchanged.
    # ------------------------------------------------------------------
    async def add_document(
        self,
        *,
        title: str,
        content: str,
        source: str = "repl",
        tags: list[str] | None = None,
    ) -> DocumentInfo:
        """Persist ``content`` as a new Document (+ N Chunks) for this user.

        Wraps :class:`~core.knowledge.ingest.DocumentIngestor` so the same
        split / embed / upsert pipeline that ``main ingest`` uses also
        runs from inside the REPL. Returns a :class:`DocumentInfo` shaped
        identically to :class:`FileKnowledgeBase`.
        """
        from core.knowledge.ingest import DocumentIngestor

        meta: dict[str, Any] = {}
        if tags:
            meta["tags"] = list(tags)

        ingestor = DocumentIngestor(
            session_factory=self._sf,
            llm=self._llm,
            user_id=self._user_id,
            embed_model=self._embed_model,
        )
        # ``source`` is the unique key for upsert; appending the title
        # ensures REPL-saved Q+A pairs don't collide on a single bare
        # ``"repl"`` source (which would overwrite the previous /save).
        unique_source = f"{source}:{uuid.uuid4().hex[:8]}"
        result = await ingestor.ingest_text(
            content,
            source=unique_source,
            title=title,
            meta=meta,
        )
        from datetime import datetime, timezone

        return DocumentInfo(
            id=str(result.document_id),
            title=title or "(untitled)",
            source=unique_source,
            tags=list(tags or []),
            chunk_count=result.chunk_count,
            char_count=result.char_count,
            # The ingest pipeline doesn't return created_at; the Document
            # row's DEFAULT now() handled it. Approximate with "now" here
            # — accurate enough for the REPL list view.
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    async def list_documents(self) -> list[DocumentInfo]:
        """Enumerate documents visible to the current user (own + shared)."""
        from sqlalchemy import func, or_, select

        from db.models import Chunk, Document

        if self._user_id is not None:
            ownership = or_(Document.user_id == self._user_id, Document.user_id.is_(None))
        else:
            ownership = Document.user_id.is_(None)

        stmt = (
            select(
                Document.id,
                Document.title,
                Document.source,
                Document.meta,
                Document.created_at,
                func.count(Chunk.id).label("chunk_count"),
                func.coalesce(func.sum(func.char_length(Chunk.content)), 0).label("char_count"),
            )
            .outerjoin(Chunk, Chunk.document_id == Document.id)
            .where(ownership)
            .group_by(Document.id)
            .order_by(Document.created_at)
        )
        async with self._sf() as s:
            rows = (await s.execute(stmt)).all()
        out: list[DocumentInfo] = []
        for r in rows:
            meta = r.meta or {}
            tags_raw = meta.get("tags") if isinstance(meta, dict) else None
            tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
            out.append(
                DocumentInfo(
                    id=str(r.id),
                    title=r.title or "(untitled)",
                    source=r.source,
                    tags=tags,
                    chunk_count=int(r.chunk_count),
                    char_count=int(r.char_count),
                    created_at=r.created_at.isoformat() if r.created_at else "",
                )
            )
        return out

    async def get_document(
        self, doc_id: str, *, max_chunks: int | None = None
    ) -> tuple[DocumentInfo, list[tuple[int, str]]] | None:
        """Return ``(info, [(seq, content), ...])`` or ``None`` if absent.

        The chunk list is ordered by ``seq``; pass ``max_chunks`` for the
        REPL preview path so we don't dump a 200-chunk doc into stdout.
        """
        from sqlalchemy import select

        from db.models import Chunk, Document

        try:
            doc_uuid = uuid.UUID(doc_id)
        except (ValueError, TypeError):
            return None

        async with self._sf() as s:
            doc = await s.scalar(select(Document).where(Document.id == doc_uuid))
            if doc is None:
                return None
            # Enforce ownership at read time even though the public lookup
            # is by id — defence in depth for the case where the REPL is
            # ever exposed across users.
            if doc.user_id is not None and doc.user_id != self._user_id:
                return None
            chunks_stmt = (
                select(Chunk.seq, Chunk.content)
                .where(Chunk.document_id == doc_uuid)
                .order_by(Chunk.seq)
            )
            if max_chunks is not None:
                chunks_stmt = chunks_stmt.limit(max_chunks)
            chunk_rows = (await s.execute(chunks_stmt)).all()
            # Pull total chunk count via a separate scalar so the preview
            # path doesn't load all chunks just to report the total.
            from sqlalchemy import func as _func

            total_chunks = await s.scalar(
                select(_func.count(Chunk.id)).where(Chunk.document_id == doc_uuid)
            )
            total_chars = await s.scalar(
                select(_func.coalesce(_func.sum(_func.char_length(Chunk.content)), 0)).where(
                    Chunk.document_id == doc_uuid
                )
            )

        meta = doc.meta or {}
        tags_raw = meta.get("tags") if isinstance(meta, dict) else None
        tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
        info = DocumentInfo(
            id=str(doc.id),
            title=doc.title or "(untitled)",
            source=doc.source,
            tags=tags,
            chunk_count=int(total_chunks or 0),
            char_count=int(total_chars or 0),
            created_at=doc.created_at.isoformat() if doc.created_at else "",
        )
        return info, [(int(r.seq), str(r.content)) for r in chunk_rows]

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document + cascade its chunks. Returns True iff one was removed."""
        from sqlalchemy import delete, select

        from db.models import Document

        try:
            doc_uuid = uuid.UUID(doc_id)
        except (ValueError, TypeError):
            return False
        async with self._sf() as s:
            # Re-check ownership before deleting to mirror get_document's
            # defence-in-depth — Document.user_id IS NULL is the shared
            # row case which we explicitly do NOT auto-delete from REPL.
            doc = await s.scalar(
                select(Document).where(Document.id == doc_uuid)
            )
            if doc is None:
                return False
            if doc.user_id is None:
                return False  # refuse to nuke shared docs from REPL
            if doc.user_id != self._user_id:
                return False
            await s.execute(delete(Document).where(Document.id == doc_uuid))
            await s.commit()
        return True


def _is_postgres(session: AsyncSession) -> bool:
    """Best-effort: did this session bind to a Postgres engine?

    Used to skip pg_trgm-specific SQL when running under SQLite (CI). We
    look at ``session.bind`` rather than the engine because some test
    fixtures replace the bind without touching the factory.
    """
    bind = session.bind
    if bind is None:
        return False
    dialect = getattr(bind, "dialect", None)
    return dialect is not None and dialect.name == "postgresql"


def _reciprocal_rank_fusion(
    *rankings: list[KnowledgeHit],
    k: int = 60,
) -> list[KnowledgeHit]:
    """Reciprocal Rank Fusion of two or more ranked hit lists.

    RRF score for a hit at rank ``r`` in a ranking is ``1 / (k + r)``;
    scores from each ranking are summed across all rankings the hit
    appears in. ``k=60`` is the standard constant from the original RRF
    paper (Cormack et al., 2009).

    Duplicate hits across rankings are merged by ``(title, source, content)``
    identity. The output is sorted by fused score descending; the final
    ``score`` is set to the fused score so the reranker can either use it
    or overwrite it.
    """
    by_key: dict[tuple[str, str, str], KnowledgeHit] = {}
    fused_score: dict[tuple[str, str, str], float] = {}

    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            key = (hit.title, hit.source, hit.content)
            if key not in by_key:
                by_key[key] = hit
            fused_score[key] = fused_score.get(key, 0.0) + 1.0 / (k + rank)

    out = [
        KnowledgeHit(
            title=hit.title,
            content=hit.content,
            score=fused_score[key],
            source=hit.source,
        )
        for key, hit in by_key.items()
    ]
    out.sort(key=lambda h: h.score, reverse=True)
    return out
