"""``/knowledge`` routes — document CRUD + retrieval."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.deps import get_current_user, get_db_session, get_session_factory
from api.schemas.common import OkResponse, Page
from api.schemas.knowledge import (
    DocumentDetailOut,
    DocumentIn,
    DocumentOut,
    DocumentUpdateIn,
    SearchHitOut,
)
from service.db.models import User
from service.errors import NotFoundError
from service.knowledge import KnowledgeService
from service.providers.runtime import build_llm_for_user

__all__ = ["router"]

router = APIRouter(tags=["knowledge"])


def _knowledge_service(session: AsyncSession, user: User) -> KnowledgeService:
    return KnowledgeService(session, user_id=user.id)


def _document_404(exc: NotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail="document not found")


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
    doc = await _knowledge_service(session, user).create_document(
        source=body.source,
        title=body.title,
        body=body.body,
    )
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
    items, total = await _knowledge_service(session, user).list_documents(page=page, size=size)
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
    try:
        doc = await _knowledge_service(session, user).get_document(document_id)
    except NotFoundError as exc:
        raise _document_404(exc) from exc
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
    try:
        doc = await _knowledge_service(session, user).update_document(
            document_id,
            title=body.title,
            body=body.body,
        )
    except NotFoundError as exc:
        raise _document_404(exc) from exc
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
    try:
        await _knowledge_service(session, user).delete_document(document_id)
    except NotFoundError as exc:
        raise _document_404(exc) from exc


@router.post(
    "/documents:reindex",
    response_model=OkResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-index the current user's documents",
)
async def reindex(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> OkResponse:
    llm, _default_model = await build_llm_for_user(session_factory, user.id)
    try:
        await _knowledge_service(session, user).reindex_documents(
            session_factory=session_factory,
            llm=llm,
            settings=request.app.state.settings,
        )
    finally:
        await llm.aclose()
    return OkResponse(ok=True)


@router.get(
    "/search",
    response_model=list[SearchHitOut],
    summary="Keyword / vector search",
)
async def search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=1024)],
    top_k: Annotated[int, Query(ge=1, le=50)] = 4,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> list[SearchHitOut]:
    llm, _default_model = await build_llm_for_user(session_factory, user.id)
    try:
        hits = await _knowledge_service(session, user).search(
            q,
            top_k=top_k,
            session_factory=session_factory,
            llm=llm,
            settings=request.app.state.settings,
        )
    finally:
        await llm.aclose()
    return [
        SearchHitOut(
            document_id=hit.document_id,
            title=hit.title,
            snippet=hit.snippet,
            score=hit.score,
        )
        for hit in hits
    ]
