"""Knowledge / document DTOs.

Change 6 persists raw content inside :attr:`Document.meta["content"]` —
the dedicated chunking + embedding pipeline lives in
``implement-rag-retrieval-pgvector`` (Change 9). Record a clean DTO shape
here so downstream changes do not need to break the wire format.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DocumentIn",
    "DocumentOut",
    "SearchHitOut",
]


class DocumentIn(BaseModel):
    """Request body for ``POST /knowledge/documents``."""

    source: Annotated[str, Field(min_length=1, max_length=512)]
    title: Annotated[str, Field(max_length=256)] | None = None
    content: Annotated[str, Field(min_length=1, max_length=10_000_000)]


class DocumentOut(BaseModel):
    """Response projection for a document row."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    title: str | None
    created_at: datetime


class SearchHitOut(BaseModel):
    """One result from ``GET /knowledge/search``."""

    document_id: uuid.UUID
    title: str | None = None
    snippet: str
    score: float
