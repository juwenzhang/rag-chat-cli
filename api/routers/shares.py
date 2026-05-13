"""``/shares`` — per-Q&A public share links.

Design notes:

* ``GET /shares/{token}`` is **unauthenticated** — anyone with the link can
  see the Q&A. Every other endpoint requires the owner.
* ``POST /shares`` is **get-or-create**: re-sharing the same Q&A returns the
  existing row instead of generating a new token (the
  ``UNIQUE(user_id, assistant_message_id)`` index makes this trivial).
* The share is a *live link*: ``GET /shares/{token}`` joins the underlying
  messages at view time. Deleting the source session/message kills the share
  via the FK CASCADE — that's the contract the user picked.
"""

from __future__ import annotations

import secrets
import string
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db_session
from api.schemas.share import (
    SharedMessageOut,
    SharePublicOut,
    ShareCreateIn,
    ShareOut,
)
from db.models import ChatSession, Message, MessageShare, Provider, User

__all__ = ["router"]

router = APIRouter(tags=["shares"])

_TOKEN_ALPHABET = string.ascii_letters + string.digits
_TOKEN_LEN = 16  # base62, ~95 bits of entropy — plenty for a public slug


def _new_token() -> str:
    return "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LEN))


async def _own_message(
    session: AsyncSession, user_id: uuid.UUID, message_id: uuid.UUID
) -> Message:
    """Fetch a message and verify it belongs to a session owned by ``user_id``.

    Returns 404 (not 403) if the message doesn't belong to the user to avoid
    leaking the existence of other users' messages.
    """
    msg = await session.get(Message, message_id)
    if msg is None:
        raise HTTPException(status_code=404, detail="message not found")
    owner_session = await session.get(ChatSession, msg.session_id)
    if owner_session is None or owner_session.user_id != user_id:
        raise HTTPException(status_code=404, detail="message not found")
    return msg


@router.post(
    "/shares",
    response_model=ShareOut,
    status_code=status.HTTP_201_CREATED,
    summary="Share a Q&A pair (get-or-create by (user, assistant_message_id))",
)
async def create_share(
    body: ShareCreateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ShareOut:
    # Verify both messages exist and belong to the user, and that they live in
    # the same chat session in the expected order (user → assistant).
    user_msg = await _own_message(session, user.id, body.user_message_id)
    asst_msg = await _own_message(session, user.id, body.assistant_message_id)
    if user_msg.session_id != asst_msg.session_id:
        raise HTTPException(status_code=400, detail="messages span sessions")
    if user_msg.role != "user" or asst_msg.role != "assistant":
        raise HTTPException(status_code=400, detail="roles must be user + assistant")
    if asst_msg.created_at < user_msg.created_at:
        raise HTTPException(status_code=400, detail="assistant must follow user")

    existing = await session.scalar(
        select(MessageShare).where(
            MessageShare.user_id == user.id,
            MessageShare.assistant_message_id == body.assistant_message_id,
        )
    )
    if existing is not None:
        return ShareOut.model_validate(existing)

    row = MessageShare(
        token=_new_token(),
        user_id=user.id,
        session_id=user_msg.session_id,
        user_message_id=body.user_message_id,
        assistant_message_id=body.assistant_message_id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ShareOut.model_validate(row)


@router.get(
    "/shares",
    response_model=list[ShareOut],
    summary="List the current user's active shares",
)
async def list_my_shares(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ShareOut]:
    rows = (
        await session.scalars(
            select(MessageShare)
            .where(MessageShare.user_id == user.id)
            .order_by(MessageShare.created_at.desc())
        )
    ).all()
    return [ShareOut.model_validate(r) for r in rows]


@router.delete(
    "/shares/{token}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a share by token (owner only)",
)
async def revoke_share(
    token: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> None:
    row = await session.scalar(
        select(MessageShare).where(MessageShare.token == token)
    )
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="share not found")
    await session.delete(row)
    await session.commit()


@router.get(
    "/shares/{token}",
    response_model=SharePublicOut,
    summary="Public — fetch a shared Q&A by token (no auth required)",
)
async def public_share(
    token: str,
    session: AsyncSession = Depends(get_db_session),
) -> SharePublicOut:
    row = await session.scalar(
        select(MessageShare).where(MessageShare.token == token)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="share not found")

    user_msg = await session.get(Message, row.user_message_id)
    asst_msg = await session.get(Message, row.assistant_message_id)
    if user_msg is None or asst_msg is None:
        # CASCADE FK should keep this in lockstep with the share row; if we
        # somehow ended up half-populated, treat it as 404 rather than 500.
        raise HTTPException(status_code=404, detail="share content unavailable")

    chat = await session.get(ChatSession, row.session_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="share content unavailable")

    # Resolve the model + provider that produced the assistant message. The
    # name lives behind a JOIN; do a cheap lookup so the share footer can
    # show "Answered by qwen2.5:7b · my-local-ollama" like the in-app view.
    provider_name: str | None = None
    if chat.provider_id is not None:
        prov = await session.get(Provider, chat.provider_id)
        if prov is not None:
            provider_name = prov.name

    return SharePublicOut(
        token=row.token,
        created_at=row.created_at,
        session_id=row.session_id,
        session_owner_id=chat.user_id,
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
