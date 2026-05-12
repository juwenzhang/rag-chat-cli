"""On-disk JSONL knowledge base for the unauthenticated CLI path.

Storage layout under ``~/.config/rag-chat/kb/`` (override via ``root=``)::

    docs.jsonl                   # one line per Document
    chunks/<doc_id>.jsonl        # one line per Chunk (incl. embedding)

Why JSONL and not SQLite?
  - Trivially diffable / inspectable with ``cat | head``.
  - No schema migration story to own — Postgres is for that.
  - ``/kb delete`` becomes ``os.remove`` on the per-doc chunks file plus a
    one-pass rewrite of ``docs.jsonl``.

Search is in-memory cosine over all chunks. We compute the query
embedding once (one Ollama round-trip) and rank stored embeddings with
stdlib ``math``. No numpy dependency — at small-to-medium scale
(< 50k chunks) this stays well under 100ms on a laptop, which is fast
enough for a local CLI.

Concurrency: single-writer assumed (the CLI process). Two concurrent
``add_document`` calls would race on ``docs.jsonl`` rewrite — that's an
accepted limitation for a local dev tool. A future move to SQLite or
fcntl-based locking is a single-file change that doesn't ripple.
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.knowledge.base import DocumentInfo, KnowledgeHit
from core.knowledge.ingest import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, split_text

if TYPE_CHECKING:
    from core.llm.client import LLMClient

__all__ = [
    "DEFAULT_KB_ROOT",
    "FileKnowledgeBase",
]

logger = logging.getLogger(__name__)


DEFAULT_KB_ROOT = Path.home() / ".config" / "rag-chat" / "kb"


def _doc_to_json(info: DocumentInfo) -> str:
    """Serialize a :class:`DocumentInfo` for ``docs.jsonl`` (one line)."""
    return json.dumps(
        {
            "id": info.id,
            "title": info.title,
            "source": info.source,
            "tags": list(info.tags),
            "chunk_count": info.chunk_count,
            "char_count": info.char_count,
            "created_at": info.created_at,
        },
        ensure_ascii=False,
    )


def _doc_from_dict(d: dict[str, Any]) -> DocumentInfo:
    """Parse one ``docs.jsonl`` line back to a :class:`DocumentInfo`."""
    tags_raw = d.get("tags") or []
    tags: list[str] = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
    return DocumentInfo(
        id=str(d.get("id") or uuid.uuid4().hex),
        title=str(d.get("title") or ""),
        source=str(d.get("source") or "local"),
        tags=tags,
        chunk_count=int(d.get("chunk_count") or 0),
        char_count=int(d.get("char_count") or 0),
        created_at=str(d.get("created_at") or ""),
    )


@dataclass(frozen=True, slots=True)
class _Chunk:
    """One stored chunk — content + its embedding vector."""

    id: str
    doc_id: str
    chunk_index: int
    content: str
    embedding: list[float]


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity in stdlib. Returns 0.0 on mismatched / zero vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class FileKnowledgeBase:
    """JSONL-backed local knowledge base.

    Implements the :class:`~core.knowledge.base.KnowledgeBase` Protocol so
    :class:`~core.chat_service.ChatService` can use it without knowing
    where the data lives. Adds curation helpers (``add_document`` /
    ``list_documents`` / ``get_document`` / ``delete_document``) used by
    the ``/kb`` and ``/save`` slash commands.

    The embedding LLM is **required** for ingestion and search. Construct
    with :meth:`from_settings` so the embed model name flows in from
    ``settings.ollama.embed_model``.
    """

    def __init__(
        self,
        root: str | Path = DEFAULT_KB_ROOT,
        *,
        llm: LLMClient | None = None,
        embed_model: str | None = None,
        min_score: float = 0.0,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        self._root = Path(root)
        self._llm = llm
        self._embed_model = embed_model
        self._min_score = min_score
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    @classmethod
    def from_settings(
        cls,
        *,
        llm: LLMClient | None = None,
        root: str | Path | None = None,
        s: Any | None = None,
    ) -> FileKnowledgeBase:
        if s is None:
            from settings import settings as _s

            s = _s
        return cls(
            root=root or DEFAULT_KB_ROOT,
            llm=llm,
            embed_model=s.ollama.embed_model,
            min_score=float(s.retrieval.min_score),
        )

    @property
    def root(self) -> Path:
        return self._root

    # ------------------------------------------------------------------
    # KnowledgeBase Protocol
    # ------------------------------------------------------------------
    async def search(self, query: str, *, top_k: int = 4) -> list[KnowledgeHit]:
        """Cosine-similarity search over all locally-stored chunks.

        Returns ``[]`` if the KB is empty, the query is whitespace, or no
        LLM is wired (no way to embed the query — we don't pretend to
        search without it).
        """
        if not query or not query.strip():
            return []
        if self._llm is None:
            return []

        chunks_dir = self._chunks_dir()
        if not chunks_dir.exists():
            return []

        try:
            vectors = await self._llm.embed([query], model=self._embed_model)
        except Exception as exc:
            logger.warning("FileKnowledgeBase: query embedding failed: %s", exc)
            return []
        if not vectors or not vectors[0]:
            return []
        query_vec = vectors[0]

        docs_by_id = {d.id: d for d in self._read_docs()}

        scored: list[tuple[float, _Chunk]] = []
        for chunks_file in chunks_dir.glob("*.jsonl"):
            for chunk in self._read_chunks(chunks_file):
                score = _cosine(query_vec, chunk.embedding)
                if score < self._min_score:
                    continue
                scored.append((score, chunk))

        scored.sort(key=lambda t: t[0], reverse=True)
        out: list[KnowledgeHit] = []
        for score, ch in scored[:top_k]:
            doc = docs_by_id.get(ch.doc_id)
            out.append(
                KnowledgeHit(
                    title=(doc.title if doc else "(untitled)") or "(untitled)",
                    content=ch.content,
                    score=score,
                    source=(doc.source if doc else "local"),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Curation API (used by /kb and /save)
    # ------------------------------------------------------------------
    async def add_document(
        self,
        *,
        title: str,
        content: str,
        source: str = "local",
        tags: list[str] | None = None,
    ) -> DocumentInfo:
        """Split → embed → persist ``content`` as a new document.

        Raises :class:`ValueError` if content is empty after stripping, or
        :class:`RuntimeError` if no LLM was wired at construction time.
        """
        if self._llm is None:
            raise RuntimeError(
                "FileKnowledgeBase.add_document requires an LLM client for embedding; "
                "construct via from_settings(llm=...)."
            )
        chunks = split_text(
            content,
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
        )
        if not chunks:
            raise ValueError("nothing to ingest: content is empty after stripping whitespace")

        vectors = await self._llm.embed(chunks, model=self._embed_model)
        if len(vectors) != len(chunks):
            raise RuntimeError(
                f"embedding model returned {len(vectors)} vectors for {len(chunks)} chunks"
            )

        doc_id = uuid.uuid4().hex
        info = DocumentInfo(
            id=doc_id,
            title=title or "(untitled)",
            source=source,
            tags=list(tags or []),
            chunk_count=len(chunks),
            char_count=sum(len(c) for c in chunks),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Write chunks first so docs.jsonl never references a missing file.
        self._chunks_dir().mkdir(parents=True, exist_ok=True)
        chunk_path = self._chunks_dir() / f"{doc_id}.jsonl"
        with chunk_path.open("w", encoding="utf-8") as f:
            for idx, (text, vec) in enumerate(zip(chunks, vectors, strict=True)):
                f.write(
                    json.dumps(
                        {
                            "id": uuid.uuid4().hex,
                            "doc_id": doc_id,
                            "chunk_index": idx,
                            "content": text,
                            "embedding": list(vec),
                        },
                        ensure_ascii=False,
                    )
                )
                f.write("\n")

        self._append_doc(info)
        return info

    async def list_documents(self) -> list[DocumentInfo]:
        """Return docs in insertion order (most recent last)."""
        return self._read_docs()

    async def get_document(
        self, doc_id: str, *, max_chunks: int | None = None
    ) -> tuple[DocumentInfo, list[tuple[int, str]]] | None:
        """Return ``(info, [(chunk_index, content), ...])`` or ``None`` if absent."""
        for d in self._read_docs():
            if d.id == doc_id:
                chunks_file = self._chunks_dir() / f"{doc_id}.jsonl"
                items: list[tuple[int, str]] = []
                if chunks_file.exists():
                    for chunk in self._read_chunks(chunks_file):
                        items.append((chunk.chunk_index, chunk.content))
                items.sort(key=lambda t: t[0])
                if max_chunks is not None:
                    items = items[:max_chunks]
                return d, items
        return None

    async def delete_document(self, doc_id: str) -> bool:
        """Remove a document + its chunks. Returns True iff a doc was deleted."""
        docs = self._read_docs()
        keep = [d for d in docs if d.id != doc_id]
        if len(keep) == len(docs):
            return False
        # Rewrite docs.jsonl atomically: write to tmp, then rename.
        self._root.mkdir(parents=True, exist_ok=True)
        tmp = self._docs_file().with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for d in keep:
                f.write(_doc_to_json(d))
                f.write("\n")
        tmp.replace(self._docs_file())

        chunks_file = self._chunks_dir() / f"{doc_id}.jsonl"
        chunks_file.unlink(missing_ok=True)
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _docs_file(self) -> Path:
        return self._root / "docs.jsonl"

    def _chunks_dir(self) -> Path:
        return self._root / "chunks"

    def _read_docs(self) -> list[DocumentInfo]:
        path = self._docs_file()
        if not path.exists():
            return []
        out: list[DocumentInfo] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(_doc_from_dict(json.loads(line)))
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.warning("FileKnowledgeBase: skipping malformed docs line: %s", exc)
        return out

    def _append_doc(self, info: DocumentInfo) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        with self._docs_file().open("a", encoding="utf-8") as f:
            f.write(_doc_to_json(info))
            f.write("\n")

    def _read_chunks(self, path: Path) -> list[_Chunk]:
        out: list[_Chunk] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "FileKnowledgeBase: skipping malformed chunk in %s: %s", path, exc
                    )
                    continue
                emb_raw = d.get("embedding") or []
                if not isinstance(emb_raw, list):
                    continue
                try:
                    embedding = [float(x) for x in emb_raw]
                except (TypeError, ValueError):
                    continue
                out.append(
                    _Chunk(
                        id=str(d.get("id") or ""),
                        doc_id=str(d.get("doc_id") or ""),
                        chunk_index=int(d.get("chunk_index") or 0),
                        content=str(d.get("content") or ""),
                        embedding=embedding,
                    )
                )
        return out
