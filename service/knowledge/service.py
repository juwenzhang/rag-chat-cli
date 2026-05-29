"""Application service for document CRUD, indexing, and search."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select

from service.db.models import Document
from service.errors import NotFoundError
from service.knowledge.ingest import DocumentIngestor
from service.knowledge.pgvector import PgvectorKnowledgeBase

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from service.llm.client import LLMClient
    from settings import Settings

__all__ = ["KnowledgeSearchHit", "KnowledgeService"]


@dataclass(frozen=True, slots=True)
class KnowledgeSearchHit:
    document_id: uuid.UUID
    title: str | None
    snippet: str
    score: float


class KnowledgeService:
    """User-scoped document service.

    HTTP routers own transport concerns; this class owns document persistence,
    indexing orchestration, and retrieval mapping.
    """

    def __init__(self, session: AsyncSession, *, user_id: uuid.UUID) -> None:
        self._session = session
        self._user_id = user_id

    async def create_document(self, *, source: str, title: str, body: str) -> Document:
        doc = Document(user_id=self._user_id, source=source, title=title, body=body)
        self._session.add(doc)
        await self._session.commit()
        await self._session.refresh(doc)
        return doc

    async def list_documents(self, *, page: int, size: int) -> tuple[list[Document], int]:
        offset = (page - 1) * size
        q = (
            select(Document)
            .where(Document.user_id == self._user_id)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        items = (await self._session.scalars(q)).all()
        total = (
            cast(
                "int",
                await self._session.scalar(
                    select(func.count(Document.id)).where(Document.user_id == self._user_id)
                ),
            )
            or 0
        )
        return list(items), total

    async def get_document(self, document_id: uuid.UUID) -> Document:
        doc = await self._session.get(Document, document_id)
        if doc is None or doc.user_id != self._user_id:
            raise NotFoundError("document not found")
        return doc

    async def update_document(
        self,
        document_id: uuid.UUID,
        *,
        title: str | None = None,
        body: str | None = None,
    ) -> Document:
        doc = await self.get_document(document_id)
        if title is not None:
            doc.title = title
        if body is not None:
            doc.body = body
        await self._session.commit()
        await self._session.refresh(doc)
        return doc

    async def delete_document(self, document_id: uuid.UUID) -> None:
        doc = await self.get_document(document_id)
        await self._session.delete(doc)
        await self._session.commit()

    async def reindex_documents(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        llm: LLMClient,
        settings: Settings,
    ) -> int:
        docs = (
            await self._session.scalars(select(Document).where(Document.user_id == self._user_id))
        ).all()
        ingestor = DocumentIngestor.from_settings(
            session_factory=session_factory,
            llm=llm,
            user_id=self._user_id,
            s=settings,
        )
        indexed = 0
        for doc in docs:
            if not doc.body.strip():
                continue
            await ingestor.ingest_text(
                doc.body,
                source=doc.source,
                title=doc.title,
                meta=doc.meta,
            )
            indexed += 1
        return indexed

    async def search(
        self,
        query: str,
        *,
        top_k: int,
        session_factory: async_sessionmaker[AsyncSession],
        llm: LLMClient,
        settings: Settings,
    ) -> list[KnowledgeSearchHit]:
        if not settings.retrieval.enabled:
            return []
        kb = PgvectorKnowledgeBase.from_settings(
            session_factory=session_factory,
            llm=llm,
            user_id=self._user_id,
            s=settings,
        )
        hits = await kb.search(query, top_k=top_k)
        out: list[KnowledgeSearchHit] = []
        for hit in hits:
            if hit.document_id is None:
                continue
            out.append(
                KnowledgeSearchHit(
                    document_id=uuid.UUID(hit.document_id),
                    title=hit.title,
                    snippet=hit.content,
                    score=hit.score,
                )
            )
        return out
