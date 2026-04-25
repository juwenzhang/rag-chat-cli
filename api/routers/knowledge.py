"""``/knowledge`` routes — document upload, reindex stub, search stub.

Chunking + embedding + real vector search ship in
``implement-rag-retrieval-pgvector`` (Change 9). For now we store the raw
content inside :attr:`Document.meta["content"]` so Change 9 has something to
consume without another migration.
"""

from __future__ import annotations

import logging
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db_session
from api.schemas.common import OkResponse, Page
from api.schemas.knowledge import DocumentIn, DocumentOut, SearchHitOut
from db.models import Document, User

__all__ = ["router"]

logger = logging.getLogger(__name__)
router = APIRouter(tags=["knowledge"])


@router.post(
    "/documents",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document (stored verbatim, indexed lazily)",
)
async def upload_document(
    body: DocumentIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DocumentOut:
    # Raw content lives inside `meta.content` until Change 9 wires up
    # chunking; keep the column NOT NULL in the meantime.
    meta = {"content": body.content}
    doc = Document(
        user_id=user.id,
        source=body.source,
        title=body.title,
        meta=meta,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return DocumentOut.model_validate(doc)


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
