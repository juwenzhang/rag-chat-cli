"""``/bookmarks`` — private favourites on individual Q&A pairs.

All endpoints require auth. ``POST`` is get-or-create; re-bookmarking the
same Q&A updates the ``note`` if one was passed.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db_session
from api.routers.shares import _own_message
from api.schemas.share import BookmarkCreateIn, BookmarkOut, SharedMessageOut
from db.models import ChatSession, Message, MessageBookmark, Provider, User
from pydantic import BaseModel, ConfigDict
from datetime import datetime

__all__ = ["router"]

router = APIRouter(tags=["bookmarks"])


class _BookmarkDetailOut(BaseModel):
    """Bookmark row + the rendered Q&A pair it points at.

    Used by ``GET /bookmarks/full`` so the bookmarks page can render
    everything in a single round-trip rather than fanning out one
    ``/shares/{token}``-style fetch per row.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    session_owner_id: uuid.UUID
    # Message refs are repeated so the bookmarks page can trigger Share /
    # Re-bookmark actions against the same Q&A without an extra round-trip.
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    note: str | None
    created_at: datetime
    user_message: SharedMessageOut
    assistant_message: SharedMessageOut


@router.post(
    "/bookmarks",
    response_model=BookmarkOut,
    status_code=status.HTTP_201_CREATED,
    summary="Bookmark a Q&A pair (get-or-create; updates note if provided)",
)
async def create_bookmark(
    body: BookmarkCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> BookmarkOut:
    user_msg = await _own_message(session, user.id, body.user_message_id)
    asst_msg = await _own_message(session, user.id, body.assistant_message_id)
    if user_msg.session_id != asst_msg.session_id:
        raise HTTPException(status_code=400, detail="messages span sessions")
    if user_msg.role != "user" or asst_msg.role != "assistant":
        raise HTTPException(status_code=400, detail="roles must be user + assistant")

    existing = await session.scalar(
        select(MessageBookmark).where(
            MessageBookmark.user_id == user.id,
            MessageBookmark.assistant_message_id == body.assistant_message_id,
        )
    )
    if existing is not None:
        if body.note is not None:
            existing.note = body.note
            await session.commit()
            await session.refresh(existing)
        return BookmarkOut.model_validate(existing)

    row = MessageBookmark(
        user_id=user.id,
        session_id=user_msg.session_id,
        user_message_id=body.user_message_id,
        assistant_message_id=body.assistant_message_id,
        note=body.note,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return BookmarkOut.model_validate(row)


@router.get(
    "/bookmarks",
    response_model=list[BookmarkOut],
    summary="List the current user's bookmarks (refs only)",
)
async def list_bookmarks(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[BookmarkOut]:
    rows = (
        await session.scalars(
            select(MessageBookmark)
            .where(MessageBookmark.user_id == user.id)
            .order_by(MessageBookmark.created_at.desc())
        )
    ).all()
    return [BookmarkOut.model_validate(r) for r in rows]


@router.get(
    "/bookmarks/full",
    response_model=list[_BookmarkDetailOut],
    summary="List bookmarks with the joined Q&A content (for the bookmarks page)",
)
async def list_bookmarks_full(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[_BookmarkDetailOut]:
    rows = (
        await session.scalars(
            select(MessageBookmark)
            .where(MessageBookmark.user_id == user.id)
            .order_by(MessageBookmark.created_at.desc())
        )
    ).all()

    out: list[_BookmarkDetailOut] = []
    for r in rows:
        user_msg = await session.get(Message, r.user_message_id)
        asst_msg = await session.get(Message, r.assistant_message_id)
        chat = await session.get(ChatSession, r.session_id)
        if user_msg is None or asst_msg is None or chat is None:
            continue  # source row vanished mid-iteration — skip silently
        provider_name: str | None = None
        if chat.provider_id is not None:
            prov = await session.get(Provider, chat.provider_id)
            if prov is not None:
                provider_name = prov.name
        out.append(
            _BookmarkDetailOut(
                id=r.id,
                session_id=r.session_id,
                session_owner_id=chat.user_id,
                user_message_id=r.user_message_id,
                assistant_message_id=r.assistant_message_id,
                note=r.note,
                created_at=r.created_at,
                user_message=SharedMessageOut(
                    role="user",
                    content=user_msg.content,
                    tokens=user_msg.tokens,
                    model=None,
                    provider_name=None,
                    created_at=user_msg.created_at,
                ),
                assistant_message=SharedMessageOut(
                    role="assistant",
                    content=asst_msg.content,
                    tokens=asst_msg.tokens,
                    model=chat.model,
                    provider_name=provider_name,
                    created_at=asst_msg.created_at,
                ),
            )
        )
    return out


@router.delete(
    "/bookmarks/{bookmark_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a bookmark",
)
async def delete_bookmark(
    bookmark_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    row = await session.get(MessageBookmark, bookmark_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="bookmark not found")
    await session.delete(row)
    await session.commit()
