"""``/chat`` routes — session CRUD + non-streaming message.

The streaming counterpart (``POST /chat/stream``) lives in
:mod:`api.routers.chat_stream`; this module exposes the one-shot
``POST /chat/messages`` variant which aggregates the
:class:`~core.chat_service.ChatService` token stream into a single reply
via :meth:`ChatService.generate_full`.

Persistence: since v1.2 the :class:`ChatService` itself writes both the
user and assistant turns into ``messages`` (via
:class:`~core.memory.chat_memory.DbChatMemory`), so this module does **not**
``session.add(Message(...))`` on its own — that would double-write.
"""

from __future__ import annotations

import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.chat_service import get_chat_service_for_user
from api.deps import get_current_user, get_db_session
from api.schemas.chat import (
    ChatSessionOut,
    ChatSessionUpdateIn,
    CreateSessionIn,
    MessageIn,
    MessageOut,
)
from api.schemas.common import Page
from core.chat_service import ChatService
from core.llm.client import ChatMessage
from core.providers import ProviderNotFoundError, get_provider
from core.titles import synthesize_preview_title
from db.models import ChatSession, Message, User

__all__ = ["router"]

router = APIRouter(tags=["chat"])


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.post(
    "/sessions",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a chat session",
)
async def create_session(
    body: CreateSessionIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionOut:
    if body.provider_id is not None:
        # Confirm the provider belongs to ``user`` before persisting the pin.
        try:
            await get_provider(
                session, user_id=user.id, provider_id=body.provider_id
            )
        except ProviderNotFoundError as exc:
            raise HTTPException(
                status_code=400, detail="provider_id does not exist"
            ) from exc

    row = ChatSession(
        user_id=user.id,
        title=body.title,
        provider_id=body.provider_id,
        model=body.model,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ChatSessionOut.model_validate(row)


@router.patch(
    "/sessions/{session_id}",
    response_model=ChatSessionOut,
    summary="Patch a chat session (title / provider / model pin)",
)
async def patch_session(
    session_id: uuid.UUID,
    body: ChatSessionUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionOut:
    row = await session.get(ChatSession, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="session not found")

    if body.title is not None:
        row.title = body.title
    if body.clear_provider_id:
        row.provider_id = None
    elif body.provider_id is not None:
        try:
            await get_provider(
                session, user_id=user.id, provider_id=body.provider_id
            )
        except ProviderNotFoundError as exc:
            raise HTTPException(
                status_code=400, detail="provider_id does not exist"
            ) from exc
        row.provider_id = body.provider_id
    if body.clear_model:
        row.model = None
    elif body.model is not None:
        row.model = body.model

    await session.commit()
    await session.refresh(row)
    return ChatSessionOut.model_validate(row)


@router.get(
    "/sessions",
    response_model=Page[ChatSessionOut],
    summary="List chat sessions owned by the current user",
)
async def list_sessions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 20,
) -> Page[ChatSessionOut]:
    offset = (page - 1) * size
    q = (
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .offset(offset)
        .limit(size)
    )
    items = (await session.scalars(q)).all()
    total_q = select(func.count(ChatSession.id)).where(ChatSession.user_id == user.id)
    total = cast("int", await session.scalar(total_q)) or 0

    # Rows where ``title`` is NULL get a preview synthesized from the first
    # user message — same fallback the CLI sidebar uses (core.titles). One
    # extra SELECT per such row; bounded by the page size.
    projected: list[ChatSessionOut] = []
    for row in items:
        out = ChatSessionOut.model_validate(row)
        if not out.title:
            first_user = await session.scalar(
                select(Message.content)
                .where(Message.session_id == row.id, Message.role == "user")
                .order_by(Message.created_at.asc())
                .limit(1)
            )
            if isinstance(first_user, str) and first_user.strip():
                out = out.model_copy(
                    update={
                        "title": synthesize_preview_title(
                            [ChatMessage(role="user", content=first_user)]
                        )
                    }
                )
        projected.append(out)

    return Page[ChatSessionOut](
        items=projected,
        page=page,
        size=size,
        total=total,
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=Page[MessageOut],
    summary="Paginate messages inside a chat session",
)
async def list_messages(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[MessageOut]:
    owner = await session.get(ChatSession, session_id)
    if owner is None or owner.user_id != user.id:
        # Return 404 rather than 403 to avoid leaking the existence of other
        # users' sessions (AGENTS.md §6 enumeration guidance).
        raise HTTPException(status_code=404, detail="session not found")

    offset = (page - 1) * size
    q = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
        .offset(offset)
        .limit(size)
    )
    items = (await session.scalars(q)).all()
    total_q = select(func.count(Message.id)).where(Message.session_id == session_id)
    total = cast("int", await session.scalar(total_q)) or 0
    return Page[MessageOut](
        items=[MessageOut.model_validate(it) for it in items],
        page=page,
        size=size,
        total=total,
    )


# ---------------------------------------------------------------------------
# Messages (non-streaming)
# ---------------------------------------------------------------------------


@router.post(
    "/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Send a user message and get the aggregated assistant reply",
)
async def post_message(
    body: MessageIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    service: ChatService = Depends(get_chat_service_for_user),
) -> MessageOut:
    owner = await session.get(ChatSession, body.session_id)
    if owner is None or owner.user_id != user.id:
        raise HTTPException(status_code=404, detail="session not found")

    # ChatService owns persistence (user + assistant rows) since v1.2; we
    # only need the aggregated result to shape the HTTP response.
    result = await _generate_reply(service, body, model=owner.model)

    # Fetch the row ChatService just wrote so the response carries a real
    # ``id`` / ``created_at``. Cheap — single index scan on (session_id, created_at).
    last_assistant = await session.scalar(
        select(Message)
        .where(Message.session_id == body.session_id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    if last_assistant is None:
        # Should not happen on the happy path (ChatService wrote it) but guard
        # just in case upstream LLM errored mid-way and memory rolled back.
        raise HTTPException(
            status_code=502,
            detail="assistant reply was not persisted",
        )
    # ``tokens`` is informational; ChatService currently doesn't fill it in
    # (usage_tokens flows through the stream ``done`` event). Patch it here
    # to keep the response shape stable with pre-v1.2.
    if result["tokens"] is not None and last_assistant.tokens is None:
        last_assistant.tokens = result["tokens"]
        await session.commit()
        await session.refresh(last_assistant)
    return MessageOut.model_validate(last_assistant)


async def _generate_reply(
    service: ChatService, body: MessageIn, *, model: str | None
) -> dict[str, int | None]:
    """Run :meth:`ChatService.generate_full` and unpack the usage field."""
    try:
        result = await service.generate_full(
            str(body.session_id),
            body.content,
            use_rag=body.use_rag,
            model=model,
        )
    finally:
        await service.aclose()

    if result["error"] is not None:
        raise HTTPException(
            status_code=502,
            detail=f"upstream LLM error: {result['error']['code']}",
        )

    usage_tokens: int | None = None
    usage = result["usage"]
    if isinstance(usage, dict):
        tok = usage.get("eval_count") or usage.get("completion_tokens")
        if isinstance(tok, int):
            usage_tokens = tok
    return {"tokens": usage_tokens}
