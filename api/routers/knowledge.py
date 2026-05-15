"""``/knowledge`` routes — document CRUD + search stub.

Documents now store markdown in a dedicated ``body`` column (matching
the wiki_pages model). ``meta`` JSONB is kept for future extensibility.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db_session
from api.schemas.common import OkResponse, Page
from api.schemas.knowledge import DocumentDetailOut, DocumentIn, DocumentOut, DocumentUpdateIn, SearchHitOut
from db.models import Document, User

__all__ = ["router"]

logger = logging.getLogger(__name__)
router = APIRouter(tags=["knowledge"])


@router.post(
    "/documents",
    response_model=DocumentDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a document",
)
async def upload_document(
    body: DocumentIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentDetailOut:
    doc = Document(
        user_id=user.id,
        source=body.source,
        title=body.title,
        body=body.body,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return DocumentDetailOut.model_validate(doc)


@router.get(
    "/documents",
    response_model=Page[DocumentOut],
    summary="List documents owned by the current user",
)
async def list_documents(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> Page[DocumentOut]:
    offset = (page - 1) * size
    q = (
        select(Document)
        .where(Document.user_id == user.id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    items = (await session.scalars(q)).all()
    total = (
        cast(
            "int",
            await session.scalar(
                select(func.count(Document.id)).where(Document.user_id == user.id)
            ),
        )
        or 0
    )
    return Page[DocumentOut](
        items=[DocumentOut.model_validate(it) for it in items],
        page=page,
        size=size,
        total=total,
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetailOut,
    summary="Fetch a single document with body",
)
async def get_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentDetailOut:
    doc = await session.get(Document, document_id)
    if doc is None or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="document not found")
    return DocumentDetailOut.model_validate(doc)


@router.patch(
    "/documents/{document_id}",
    response_model=DocumentDetailOut,
    summary="Update a document's title and/or body",
)
async def update_document(
    document_id: uuid.UUID,
    body: DocumentUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentDetailOut:
    doc = await session.get(Document, document_id)
    if doc is None or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="document not found")
    if body.title is not None:
        doc.title = body.title
    if body.body is not None:
        doc.body = body.body
    await session.commit()
    await session.refresh(doc)
    return DocumentDetailOut.model_validate(doc)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document (also drops any chunks referencing it)",
)
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    doc = await session.get(Document, document_id)
    if doc is None or doc.user_id != user.id:
        raise HTTPException(status_code=404, detail="document not found")
    # ``Chunk`` rows reference ``Document`` via FK ON DELETE CASCADE, so
    # they go away with the document — no manual fan-out needed.
    await session.delete(doc)
    await session.commit()


@router.post(
    "/documents:reindex",
    response_model=OkResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request an asynchronous re-index pass (queue lands in P8)",
)
async def reindex(user: User = Depends(get_current_user)) -> OkResponse:
    # TODO(Change 8, add-redis-and-workers): enqueue `ingest_document` for
    # every document owned by this user. Return 202 with a task id list.
    logger.info("reindex.requested user_id=%s (queue not wired yet)", user.id)
    return OkResponse(ok=True)


@router.get(
    "/search",
    response_model=list[SearchHitOut],
    summary="Keyword / vector search (returns empty until Change 9)",
)
async def search(
    q: Annotated[str, Query(min_length=1, max_length=1024)],
    top_k: Annotated[int, Query(ge=1, le=50)] = 4,
    user: User = Depends(get_current_user),
) -> list[SearchHitOut]:
    del q, top_k, user  # real retrieval is Change 9
    logger.info("search not implemented yet — returning empty result")
    return []
