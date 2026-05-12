"""Knowledge retrieval (RAG).

Public surface:

* :class:`KnowledgeBase` — async retriever Protocol.
* :class:`KnowledgeHit` — single retrieved chunk.
* :class:`FileKnowledgeBase` — on-disk JSONL retriever (unauth / offline path).
* :class:`PgvectorKnowledgeBase` — production retriever over Postgres + pgvector.
"""

from __future__ import annotations

from core.knowledge.base import DocumentInfo, KnowledgeBase, KnowledgeHit
from core.knowledge.ingest import DocumentIngestor, IngestionResult, split_text
from core.knowledge.local import FileKnowledgeBase
from core.knowledge.pgvector import PgvectorKnowledgeBase
from core.knowledge.reflect import KB_REFLECT_PROMPT, ReflectionCritic, ReflectionResult
from core.knowledge.rerank import NoopReranker, Reranker

__all__ = [
    "KB_REFLECT_PROMPT",
    "DocumentInfo",
    "DocumentIngestor",
    "FileKnowledgeBase",
    "IngestionResult",
    "KnowledgeBase",
    "KnowledgeHit",
    "NoopReranker",
    "PgvectorKnowledgeBase",
    "ReflectionCritic",
    "ReflectionResult",
    "Reranker",
    "split_text",
]
