"""Chunk model — the granular unit used by RAG retrieval.

The ``embedding`` column is the tricky bit:

* **Postgres (pgvector)**: real ``VECTOR(dim)`` column; an ivfflat index
  will be created in the Alembic migration for cosine-similarity search.
* **SQLite (tests / CI)**: pgvector has no SQLite dialect. We swap the
  type to :class:`_JSONVectorFallback` (a :class:`TypeDecorator` around
  ``JSON``) which serialises ``list[float]`` as JSON text. Round-trips
  work; similarity queries do not — tests that actually need ivfflat
  carry the ``@pytest.mark.pg`` marker.

Dimension comes from ``settings.retrieval.embed_dim`` at *import* time.
If a future change lets users pick a different model, bump the setting
and emit a new migration.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON as SAJSON
from sqlalchemy import ForeignKey, Index, Integer, Text, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import TypeEngine

from db.base import Base
from db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["EMBED_DIM", "Chunk"]


def _resolve_embed_dim() -> int:
    """Read the embedding dim from settings, defaulting to 768.

    Wrapped in a helper so that the import does not fail if settings cannot
    load (e.g. under ``alembic`` bootstrap with no ``.env``).
    """

    try:
        from settings import settings

        return int(settings.retrieval.embed_dim)
    except Exception:
        return 768


EMBED_DIM: int = _resolve_embed_dim()


class _JSONVectorFallback(TypeDecorator[list[float]]):
    """Stores ``list[float]`` as JSON text; used on SQLite where pgvector
    has no dialect."""

    impl = SAJSON
    cache_ok = True

    def process_bind_param(self, value: list[float] | None, dialect: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(list(value))

    def process_result_value(
        self, value: str | list[float] | None, dialect: Any
    ) -> list[float] | None:
        if value is None:
            return None
        if isinstance(value, list):
            return [float(x) for x in value]
        return [float(x) for x in json.loads(value)]


# PG gets the real Vector; other dialects get the JSON fallback.
_VectorType: TypeEngine[Any] = Vector(EMBED_DIM).with_variant(_JSONVectorFallback(), "sqlite")


class Chunk(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(_VectorType, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        # The ivfflat index is only meaningful on Postgres; ``postgresql_*``
        # kwargs are simply ignored by other dialects.
        Index(
            "ix_chunks_embedding_ivfflat",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"lists": 100},
        ),
    )
