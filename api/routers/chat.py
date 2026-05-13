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

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
    MessageUpdateIn,
)
from api.schemas.common import Page
from api.schemas.share import ForkFromShareIn
from core.chat_service import ChatService
from core.llm.client import ChatMessage
from core.providers import ProviderNotFoundError, get_provider
from core.titles import synthesize_preview_title
from db.models import ChatSession, Message, MessageShare, User, WikiPage

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
    if body.pinned is not None:
        row.pinned = body.pinned

    await session.commit()
    await session.refresh(row)
    return ChatSessionOut.model_validate(row)


@router.post(
    "/sessions/from-share",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Fork a shared Q&A into a brand-new session owned by the caller",
)
async def fork_from_share(
    body: ForkFromShareIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionOut:
    """Anyone who can read ``GET /shares/{token}`` can fork it. We don't gate
    on session ownership — the whole point is to let viewers continue a
    public Q&A in their own thread.

    Implementation: load the original Q&A messages, build a new session, and
    copy the two messages over. The new session inherits the original's
    provider/model pin (so the conversation feels continuous) but its own
    fresh ``id``/``created_at``.
    """
    share = await session.scalar(
        select(MessageShare).where(MessageShare.token == body.token)
    )
    if share is None:
        raise HTTPException(status_code=404, detail="share not found")

    user_msg = await session.get(Message, share.user_message_id)
    asst_msg = await session.get(Message, share.assistant_message_id)
    src_session = await session.get(ChatSession, share.session_id)
    if user_msg is None or asst_msg is None or src_session is None:
        raise HTTPException(status_code=404, detail="share content unavailable")

    new_session = ChatSession(
        user_id=user.id,
        title=src_session.title,
        provider_id=src_session.provider_id,
        model=src_session.model,
    )
    session.add(new_session)
    await session.flush()  # need new_session.id before adding messages

    forked_user = Message(
        session_id=new_session.id,
        role="user",
        content=user_msg.content,
    )
    forked_asst = Message(
        session_id=new_session.id,
        role="assistant",
        content=asst_msg.content,
        tokens=asst_msg.tokens,
    )
    session.add_all([forked_user, forked_asst])
    await session.commit()
    await session.refresh(new_session)
    return ChatSessionOut.model_validate(new_session)


@router.post(
    "/sessions/from-wiki/{page_id}",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Spin up a new chat session seeded with a wiki page's content",
)
async def session_from_wiki(
    page_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ChatSessionOut:
    """Cross-module bridge from the wiki editor's "Ask AI" button.

    Behaviour: create a new session titled after the wiki page, then
    write **one user message** that quotes the page so the next stream
    call has it as turn-1 context. We deliberately stop short of also
    generating an assistant reply — the user lands in an empty thread
    and types whatever they want to ask, with the page already on the
    transcript above. That keeps the LLM call (and its cost) opt-in.
    """
    # Permission check: resolve the wiki and use its access model
    # (handles both org_wide and private wikis). Import lazily to
    # avoid a circular import with the wiki router.
    from api.routers.wiki import _require_wiki_role
    from db.models import Wiki

    page = await session.get(WikiPage, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="page not found")
    wiki = await session.get(Wiki, page.wiki_id)
    if wiki is None:
        raise HTTPException(status_code=404, detail="page not found")
    await _require_wiki_role(session, wiki, user.id, "viewer")

    new_session = ChatSession(
        user_id=user.id,
        title=f"About “{page.title}”",
    )
    session.add(new_session)
    await session.flush()

    # ``page.body`` is markdown text — feed it verbatim into the
    # seed message. The model will see it as a markdown blob, which it
    # handles natively.
    text = page.body.strip() or "(empty page)"
    seed = (
        f"I want to ask about this wiki page titled “{page.title}”. "
        f"Here's its content for context:\n\n{text}\n\n"
        f"(My questions follow.)"
    )
    session.add(
        Message(session_id=new_session.id, role="user", content=seed)
    )
    await session.commit()
    await session.refresh(new_session)
    return ChatSessionOut.model_validate(new_session)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session (and cascade its messages)",
)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    row = await session.get(ChatSession, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="session not found")
    await session.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
        .order_by(ChatSession.pinned.desc(), ChatSession.updated_at.desc())
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
# Message edit / delete — used by the chat UI's "edit & re-run" affordance
# and trim-history operations. These don't touch the LLM; re-running is a
# separate POST /chat/stream call after the edit lands.
# ---------------------------------------------------------------------------


async def _own_message_row(
    session: AsyncSession, user_id: uuid.UUID, message_id: uuid.UUID
) -> Message:
    """Resolve a message row and verify the caller owns its session.

    Returns 404 (not 403) on cross-user access to avoid leaking ids.
    """
    msg = await session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="message not found")
    owner = await session.get(ChatSession, msg.session_id)
    if owner is None or owner.user_id != user_id:
        raise HTTPException(status_code=404, detail="message not found")
    return msg


@router.patch(
    "/messages/{message_id}",
    response_model=MessageOut,
    summary="Edit a stored message's content",
)
async def update_message(
    message_id: uuid.UUID,
    body: MessageUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MessageOut:
    msg = await _own_message_row(session, user.id, message_id)
    msg.content = body.content
    await session.commit()
    await session.refresh(msg)
    return MessageOut.model_validate(msg)


@router.delete(
    "/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a single stored message",
)
async def delete_message(
    message_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    msg = await _own_message_row(session, user.id, message_id)
    await session.delete(msg)
    await session.commit()


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
