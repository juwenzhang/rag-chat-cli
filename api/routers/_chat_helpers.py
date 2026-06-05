"""Cross-router helpers shared by ``api.routers.chat*``.

These are HTTP-shape utilities — they raise :class:`fastapi.HTTPException`
or work directly off SQLAlchemy ``AsyncSession`` — so they live in the
api/routers/ tree (not in ``service/``). The leading underscore on the
filename signals "private to api.routers".
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from service.db.models import ChatSession, Message, Provider, UserPreference

__all__ = [
    "own_message_row",
    "previous_user_content",
    "require_session_owner",
    "resolve_provider_name",
]


async def require_session_owner(
    session: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    detail: str = "session not found",
) -> ChatSession:
    """Load a chat session and verify ``user_id`` owns it.

    Returns 404 (not 403) on cross-user access — same pattern as
    ``own_message_row``, follows AGENTS.md §6 to avoid leaking the
    existence of other users' sessions.
    """
    row = await session.get(ChatSession, session_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(status_code=404, detail=detail)
    return row


async def own_message_row(
    session: AsyncSession,
    user_id: uuid.UUID,
    message_id: uuid.UUID,
) -> Message:
    """Resolve a message and verify ``user_id`` owns its session.

    404 on missing or cross-user access (don't leak ids).
    """
    msg = await session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="message not found")
    owner = await session.get(ChatSession, msg.session_id)
    if owner is None or owner.user_id != user_id:
        raise HTTPException(status_code=404, detail="message not found")
    return msg


async def previous_user_content(session: AsyncSession, msg: Message) -> str | None:
    """Most recent user-role message in the same session at-or-before ``msg``.

    Used by evaluation to recover the question that prompted ``msg``.
    """
    return await session.scalar(
        select(Message.content)
        .where(
            Message.session_id == msg.session_id,
            Message.role == "user",
            Message.created_at <= msg.created_at,
        )
        .order_by(Message.created_at.desc())
        .limit(1)
    )


async def resolve_provider_name(
    session: AsyncSession,
    *,
    owner: ChatSession,
    user_id: uuid.UUID,
) -> str | None:
    """Return the provider display name for a chat session, or ``None``.

    Resolution order:
      1. ``owner.provider_id`` (per-session pin)
      2. ``user_preferences.default_provider_id`` (account default)

    The provider must belong to ``user_id`` — defence-in-depth against a
    stale pin that points at a deleted-and-recycled UUID.
    """
    provider_id = owner.provider_id
    if provider_id is None:
        pref = await session.get(UserPreference, user_id)
        if pref is not None:
            provider_id = pref.default_provider_id
    if provider_id is None:
        return None
    prov = await session.get(Provider, provider_id)
    if prov is None or prov.user_id != user_id:
        return None
    return prov.name
