"""Knowledge retrieval (RAG).

Public surface:

* :class:`KnowledgeBase` — async retriever Protocol.
* :class:`KnowledgeHit` — single retrieved chunk.
* :class:`PgvectorKnowledgeBase` — production retriever over Postgres + pgvector.
"""

from __future__ import annotations

from service.knowledge.base import DocumentInfo, KnowledgeBase, KnowledgeHit
from service.knowledge.ingest import DocumentIngestor, IngestionResult, split_text
from service.knowledge.pgvector import PgvectorKnowledgeBase
from service.knowledge.reflect import KB_REFLECT_PROMPT, ReflectionCritic, ReflectionResult
from service.knowledge.rerank import NoopReranker, Reranker
from service.knowledge.service import KnowledgeSearchHit, KnowledgeService

__all__ = [
    "KB_REFLECT_PROMPT",
    "DocumentInfo",
    "DocumentIngestor",
    "IngestionResult",
    "KnowledgeBase",
    "KnowledgeHit",
    "KnowledgeSearchHit",
    "KnowledgeService",
    "NoopReranker",
    "PgvectorKnowledgeBase",
    "ReflectionCritic",
    "ReflectionResult",
    "Reranker",
    "split_text",
]
