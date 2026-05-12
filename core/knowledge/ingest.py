"""Document ingestion pipeline (#10 P2.2).

Splits text → embeds chunks → writes :class:`db.models.Document` +
:class:`db.models.Chunk` rows. Used by:

* the ``main.py ingest`` CLI (#11) — bulk file ingestion;
* future ``POST /knowledge/documents`` API route — web upload.

Idempotent on ``(user_id, source)``: re-ingesting the same source updates
the existing Document row and replaces its chunks (FK cascade does the
delete). This keeps the chunks table from accumulating dead duplicates as
docs evolve.

Chunking strategy is intentionally simple in this first pass: fixed-width
character windows with a small overlap. A smarter splitter (sentence-aware,
markdown-aware) can replace ``split_text`` later without touching the
embed/persist side.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.llm.client import LLMClient, LLMError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = [
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "DocumentIngestor",
    "IngestionResult",
    "split_text",
]


logger = logging.getLogger(__name__)


# Character-based defaults. ~512 chars is roughly 128 tokens for English
# (rule of thumb 1 token ≈ 4 chars). Overlap keeps semantic context across
# boundaries so a query can match a chunk whose answer straddles two windows.
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Summary returned to the caller after a successful ingest."""

    document_id: uuid.UUID
    chunk_count: int
    char_count: int


def split_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split ``text`` into overlapping fixed-width windows.

    Empty / whitespace-only input returns ``[]``. ``chunk_overlap`` is
    clamped to ``< chunk_size`` so the step is always positive.
    """
    cleaned = text.strip()
    if not cleaned:
        return []
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    overlap = max(0, min(chunk_overlap, chunk_size - 1))
    step = chunk_size - overlap

    out: list[str] = []
    i = 0
    while i < len(cleaned):
        chunk = cleaned[i : i + chunk_size]
        if chunk.strip():
            out.append(chunk)
        if i + chunk_size >= len(cleaned):
            break
        i += step
    return out


class DocumentIngestor:
    """Ingest source text into the ``documents`` + ``chunks`` tables.

    Designed for CLI / API use; instances are cheap to construct and hold
    no per-document state. ``user_id`` may be ``None`` to ingest a shared
    document (visible to every user via :class:`PgvectorKnowledgeBase`).
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        llm: LLMClient,
        user_id: uuid.UUID | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        embed_model: str | None = None,
    ) -> None:
        self._sf = session_factory
        self._llm = llm
        self._user_id = user_id
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._embed_model = embed_model

    @classmethod
    def from_settings(
        cls,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        llm: LLMClient,
        user_id: uuid.UUID | None = None,
        s: Any | None = None,
    ) -> DocumentIngestor:
        if s is None:
            from settings import settings as _s

            s = _s
        return cls(
            session_factory=session_factory,
            llm=llm,
            user_id=user_id,
            embed_model=s.ollama.embed_model,
        )

    # ------------------------------------------------------------------
    # Public ingest entrypoints
    # ------------------------------------------------------------------
    async def ingest_text(
        self,
        text: str,
        *,
        source: str,
        title: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> IngestionResult:
        """Split → embed → persist ``text`` as a Document + N Chunks.

        Idempotent on ``(user_id, source)``: if a Document with this source
        already exists for ``user_id``, its old chunks are dropped (FK
        cascade) and replaced.
        """
        chunks = split_text(
            text,
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )
        if not chunks:
            raise ValueError("nothing to ingest: text is empty after stripping whitespace")

        # Embed all chunks up-front so we don't open the DB session before
        # the expensive LLM round-trip. Ollama embeds one prompt per HTTP
        # call; for now we keep it sequential — parallelism can come later
        # (#22 / #23) without touching this public API.
        try:
            vectors = await self._llm.embed(chunks, model=self._embed_model)
        except LLMError:
            raise
        if len(vectors) != len(chunks):
            raise LLMError(
                f"embedding model returned {len(vectors)} vectors "
                f"for {len(chunks)} chunks (mismatched count)"
            )

        from sqlalchemy import delete, select

        from db.models import Chunk, Document

        async with self._sf() as s:
            doc_id = await self._upsert_document(
                s,
                source=source,
                title=title,
                meta=meta or {},
            )
            # Wipe prior chunks for idempotency.
            await s.execute(delete(Chunk).where(Chunk.document_id == doc_id))
            for seq, (content, vec) in enumerate(zip(chunks, vectors, strict=True)):
                s.add(
                    Chunk(
                        document_id=doc_id,
                        seq=seq,
                        content=content,
                        embedding=vec,
                        token_count=None,
                    )
                )
            await s.commit()

            # Re-read the document_id (unchanged but explicit) to keep the
            # caller agnostic to upsert mechanics.
            final_id = await s.scalar(select(Document.id).where(Document.id == doc_id))
        assert final_id is not None  # we just upserted it
        return IngestionResult(
            document_id=final_id,
            chunk_count=len(chunks),
            char_count=sum(len(c) for c in chunks),
        )

    async def ingest_file(
        self,
        path: str | Path,
        *,
        title: str | None = None,
        meta: dict[str, Any] | None = None,
        encoding: str = "utf-8",
    ) -> IngestionResult:
        """Read ``path`` as text and ingest it. ``source`` defaults to the path."""
        # Sync filesystem IO inside an async method is acceptable here:
        # ``ingest_file`` runs from one-shot CLI commands and worker
        # handlers, not the request hot path. Reaching for anyio.path
        # would add a dependency without a real concurrency win.
        p = Path(path)
        text = p.read_text(encoding=encoding)  # noqa: ASYNC240
        return await self.ingest_text(
            text,
            source=str(p.resolve()),  # noqa: ASYNC240
            title=title or p.stem,
            meta=meta,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _upsert_document(
        self,
        s: AsyncSession,
        *,
        source: str,
        title: str | None,
        meta: dict[str, Any],
    ) -> uuid.UUID:
        """Return an existing Document.id matching (user_id, source) or insert one.

        We don't rely on a DB-level UNIQUE constraint because the migration
        in :mod:`alembic.versions.0001_init` doesn't define one; the lookup
        is a simple SELECT keyed by (user_id, source). Multiple races could
        theoretically write twice — acceptable for this ingestion path,
        which runs from the CLI or per-request and is not multi-writer.
        """
        from sqlalchemy import select

        from db.models import Document

        stmt = select(Document).where(
            Document.user_id.is_(self._user_id) if self._user_id is None else Document.user_id == self._user_id,
            Document.source == source,
        )
        existing = (await s.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            if title is not None:
                existing.title = title
            if meta:
                existing.meta = meta
            await s.flush()
            return existing.id

        doc = Document(
            user_id=self._user_id,
            source=source,
            title=title,
            meta=meta,
        )
        s.add(doc)
        await s.flush()
        return doc.id
