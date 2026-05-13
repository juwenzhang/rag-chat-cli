"""Server-Sent Events endpoint for streaming chat.

One-way stream from server to client — the companion bidirectional variant
lives in :mod:`api.routers.chat_ws`. The two share the same event schema
(:mod:`api.streaming.protocol`, see also ``docs/STREAM_PROTOCOL.md``) and
are both backed by :meth:`core.chat_service.ChatService.generate`.

Since v1.2 the :class:`ChatService` is wired with :class:`DbChatMemory`, so
persistence happens **inside** the service. This module no longer writes
``messages`` rows itself — doing so would double-write.

Transport headers:
* ``Cache-Control: no-cache`` — clients must not replay old frames.
* ``X-Accel-Buffering: no`` — tells nginx / proxies to pass bytes through
  immediately. Without this the browser sees the whole response in one go.
* ``Connection: keep-alive`` — defensive; modern HTTP/1.1 defaults already
  keep the connection open but stating it explicitly is cheap.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.chat_service import get_chat_service_for_user
from api.deps import get_current_user, get_db_session
from api.schemas.chat import MessageIn
from api.streaming.protocol import ErrorEvent, coerce_event
from api.streaming.sse import event_to_sse, merge_with_keepalive
from core.chat_service import ChatService
from db.models import ChatSession, Message, Provider, User

__all__ = ["router"]

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


SSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache, no-transform",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@router.post(
    "/stream",
    summary="Stream an assistant reply as SSE (text/event-stream)",
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": (
                "Server-Sent Events stream. Each frame is `event: <type>` + `data: <json>`. "
                "Event types: `retrieval`, `token`, `thought`, `tool_call`, `tool_result`, "
                "`done`, `error`. Schema: `api.streaming.protocol.StreamEvent`. "
                "Full vocabulary in `docs/STREAM_PROTOCOL.md`."
            ),
        },
    },
)
async def chat_stream(
    body: MessageIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    service: ChatService = Depends(get_chat_service_for_user),
) -> StreamingResponse:
    # Own the session's user / existence check up-front so 404 / 403 come
    # back as proper JSON instead of a half-opened SSE stream.
    owner = await session.get(ChatSession, body.session_id)
    if owner is None or owner.user_id != user.id:
        raise HTTPException(status_code=404, detail="session not found")

    # Per-session model pin (Sprint 2). NULL → ChatService uses its
    # construction-time default.
    session_model = owner.model

    # Resolve provider name once, up-front, so we can stamp it onto the ``done``
    # event for the UI footer ("answered by qwen2.5:7b on local-ollama"). Falls
    # back to the user's default provider when the session has no pin.
    provider_name: str | None = None
    provider_id_for_label = owner.provider_id
    if provider_id_for_label is None:
        from db.models import UserPreference

        pref = await session.get(UserPreference, user.id)
        if pref is not None:
            provider_id_for_label = pref.default_provider_id
    if provider_id_for_label is not None:
        prov = await session.get(Provider, provider_id_for_label)
        if prov is not None and prov.user_id == user.id:
            provider_name = prov.name

    async def _byte_stream() -> AsyncIterator[bytes]:
        try:
            async for raw_event in service.generate(
                str(body.session_id),
                body.content,
                use_rag=body.use_rag,
                model=session_model,
            ):
                # Inject provider_name on the done frame so the UI footer can
                # render "qwen2.5:7b · local-ollama". ChatService is provider-
                # agnostic — we add the label here at the API edge.
                if raw_event.get("type") == "done" and provider_name:
                    raw_event = {**raw_event, "provider_name": provider_name}
                try:
                    event = coerce_event(raw_event)
                except Exception:
                    logger.warning("dropping malformed event: %r", raw_event)
                    event = ErrorEvent(code="PROTOCOL", message="malformed event")
                yield event_to_sse(event)
        except Exception as exc:
            logger.exception("chat_stream blew up mid-flight")
            yield event_to_sse(ErrorEvent(code="INTERNAL", message=str(exc)))
        finally:
            await service.aclose()

    return StreamingResponse(
        merge_with_keepalive(_byte_stream()),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


class RegenerateIn(BaseModel):
    """Body for ``POST /chat/stream/regenerate``.

    The session is identified by ``session_id``; the endpoint
    automatically picks the trailing assistant message (if any) to
    discard and regenerates from the preceding user turn. No new user
    content is accepted — by design, regenerate is a "do over" against
    the existing transcript.
    """

    session_id: uuid.UUID
    use_rag: bool = False


@router.post(
    "/stream/regenerate",
    summary="Re-stream the last assistant reply (or generate one for a "
    "user turn that has none yet)",
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": (
                "Same SSE event vocabulary as ``POST /chat/stream``. The "
                "old assistant turn (if any) is deleted before streaming "
                "begins, so the client should clear it from its UI on "
                "receipt of the first frame."
            ),
        },
    },
)
async def chat_stream_regenerate(
    body: RegenerateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    service: ChatService = Depends(get_chat_service_for_user),
) -> StreamingResponse:
    """Re-run the LLM against the existing transcript.

    Two callers feed into this endpoint:

    * The chat UI's "Regenerate" button — there's a trailing assistant
      message we want to throw out and try again.
    * The wiki "Ask AI" landing flow — the session was seeded with a
      user message but no reply was ever generated; the chat view
      auto-fires this on first hydrate.

    Both reduce to "make the conversation end on a fresh assistant
    reply"; we don't need separate routes.
    """
    owner = await session.get(ChatSession, body.session_id)
    if owner is None or owner.user_id != user.id:
        raise HTTPException(status_code=404, detail="session not found")

    # Walk back from the end of the transcript: drop the trailing
    # assistant turn (and any tool turns it produced) so the next call
    # generates against a clean "...user → ?" history.
    while True:
        last = await session.scalar(
            select(Message)
            .where(Message.session_id == body.session_id)
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        if last is None:
            raise HTTPException(
                status_code=400,
                detail="session has no messages to regenerate from",
            )
        if last.role == "user":
            break  # found the anchor turn
        await session.delete(last)
        await session.commit()

    user_text = last.content

    # ── below mirrors ``chat_stream`` — provider label + SSE stream.
    session_model = owner.model
    provider_name: str | None = None
    provider_id_for_label = owner.provider_id
    if provider_id_for_label is None:
        from db.models import UserPreference

        pref = await session.get(UserPreference, user.id)
        if pref is not None:
            provider_id_for_label = pref.default_provider_id
    if provider_id_for_label is not None:
        prov = await session.get(Provider, provider_id_for_label)
        if prov is not None and prov.user_id == user.id:
            provider_name = prov.name

    async def _byte_stream() -> AsyncIterator[bytes]:
        try:
            async for raw_event in service.generate(
                str(body.session_id),
                user_text,
                use_rag=body.use_rag,
                model=session_model,
                # The user message already lives in history — don't
                # double-write it.
                persist_user=False,
            ):
                if raw_event.get("type") == "done" and provider_name:
                    raw_event = {**raw_event, "provider_name": provider_name}
                try:
                    event = coerce_event(raw_event)
                except Exception:
                    logger.warning("dropping malformed event: %r", raw_event)
                    event = ErrorEvent(code="PROTOCOL", message="malformed event")
                yield event_to_sse(event)
        except Exception as exc:
            logger.exception("chat_stream_regenerate blew up mid-flight")
            yield event_to_sse(ErrorEvent(code="INTERNAL", message=str(exc)))
        finally:
            await service.aclose()

    return StreamingResponse(
        merge_with_keepalive(_byte_stream()),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
