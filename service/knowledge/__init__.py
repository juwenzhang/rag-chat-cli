"""Knowledge retrieval (RAG).

Public surface:

* :class:`KnowledgeBase` — async retriever Protocol.
* :class:`KnowledgeHit` — single retrieved chunk.
* :class:`FileKnowledgeBase` — on-disk JSONL retriever (unauth / offline path).
* :class:`PgvectorKnowledgeBase` — production retriever over Postgres + pgvector.
"""

from __future__ import annotations

from service.knowledge.base import DocumentInfo, KnowledgeBase, KnowledgeHit
from service.knowledge.ingest import DocumentIngestor, IngestionResult, split_text
from service.knowledge.local import FileKnowledgeBase
from service.knowledge.pgvector import PgvectorKnowledgeBase
from service.knowledge.reflect import KB_REFLECT_PROMPT, ReflectionCritic, ReflectionResult
from service.knowledge.rerank import NoopReranker, Reranker

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
