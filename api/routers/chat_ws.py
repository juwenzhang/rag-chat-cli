"""WebSocket endpoint for bidirectional streaming chat.

Wire protocol (JSON frames):

* client → server:
    ``{"type": "user_message", "session_id": "<uuid>", "content": "...", "use_rag": false}``
    ``{"type": "abort"}``   # stop the current generation

* server → client (all event types from :mod:`api.streaming.protocol`):
    ``{"type": "retrieval",   "hits": [...]}``
    ``{"type": "token",       "delta": "..."}``
    ``{"type": "thought",     "text": "..."}``                # P1.5 — model reasoning
    ``{"type": "tool_call",   "tool_call_id": ..., "tool_name": ..., "arguments": {...}}``
    ``{"type": "tool_result", "tool_call_id": ..., "tool_name": ..., "content": "...", "is_error": false}``
    ``{"type": "done",        "message_id": "...", "usage": {...}}``
    ``{"type": "error",       "code": "...", "message": "..."}``

See ``docs/STREAM_PROTOCOL.md`` for the full vocabulary and field rules.

One generation per connection for now — the client is expected to close
after ``done`` / ``error``. Keeping it minimal makes reasoning about abort
vastly simpler; multi-turn over the same socket can land in a later change.

Since v1.2 the :class:`ChatService` owns persistence (via
:class:`DbChatMemory`); this module no longer writes ``messages`` rows on
its own.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from api.chat_service import get_chat_service_for_user
from api.deps import authenticate_ws
from api.streaming.protocol import ErrorEvent, coerce_event
from core.chat_service import ChatService
from core.streaming.abort import AbortContext
from db.models import ChatSession
from db.session import current_session_factory

__all__ = ["router"]

logger = logging.getLogger(__name__)
router = APIRouter()


#: WebSocket close codes we care about (4xxx = application-defined).
WS_CLOSE_NORMAL = 1000
WS_CLOSE_PROTOCOL = 4400
WS_CLOSE_NOT_FOUND = 4404


@router.websocket("/ws/chat")
async def chat_ws(
    ws: WebSocket,
    service: ChatService = Depends(get_chat_service_for_user),
) -> None:
    """Bidirectional streaming chat. Authenticated via subprotocol or `?token=`."""

    user = await authenticate_ws(ws)
    if user is None:
        # authenticate_ws already closed with 4401; still need to dispose the
        # service dep FastAPI resolved for us.
        await service.aclose()
        return

    abort_ctx = AbortContext()

    # Reader task watches for {"type": "abort"} — or any disconnect — and
    # flips the abort context. The main task, which is feeding tokens, polls
    # that context between yields in ``ChatService.generate``.
    reader_task: asyncio.Task[None] | None = None

    async def _reader() -> None:
        try:
            while True:
                msg = await ws.receive_json()
                if isinstance(msg, dict) and msg.get("type") == "abort":
                    abort_ctx.abort()
                    return
                # Ignore unknown messages; the spec only defines abort here.
        except WebSocketDisconnect:
            abort_ctx.abort()
        except Exception:
            # json parse errors etc. — treat as abort rather than crashing
            # the whole endpoint. Client will see the socket close below.
            logger.exception("ws reader error")
            abort_ctx.abort()

    try:
        # 1) Expect the first message to be user_message.
        try:
            first = await ws.receive_json()
        except WebSocketDisconnect:
            return
        if not isinstance(first, dict) or first.get("type") != "user_message":
            await _safe_send(
                ws,
                ErrorEvent(code="PROTOCOL", message="expected user_message").model_dump(),
            )
            await ws.close(code=WS_CLOSE_PROTOCOL)
            return

        try:
            session_uuid = uuid.UUID(str(first.get("session_id")))
        except (ValueError, TypeError):
            await _safe_send(
                ws,
                ErrorEvent(code="PROTOCOL", message="invalid session_id").model_dump(),
            )
            await ws.close(code=WS_CLOSE_PROTOCOL)
            return

        content = first.get("content")
        if not isinstance(content, str) or not content.strip():
            await _safe_send(
                ws,
                ErrorEvent(code="PROTOCOL", message="empty content").model_dump(),
            )
            await ws.close(code=WS_CLOSE_PROTOCOL)
            return

        use_rag = bool(first.get("use_rag", False))

        # 2) Verify ownership of the chat session.
        sf = current_session_factory()
        async with sf() as session:
            owner = await session.get(ChatSession, session_uuid)
            if owner is None or owner.user_id != user.id:
                await _safe_send(
                    ws,
                    ErrorEvent(code="NOT_FOUND", message="session not found").model_dump(),
                )
                await ws.close(code=WS_CLOSE_NOT_FOUND)
                return

        # 3) Kick off the reader (for abort / disconnect) and start streaming.
        reader_task = asyncio.create_task(_reader())
        await _stream_reply(
            ws,
            service=service,
            session_uuid=session_uuid,
            content=content,
            use_rag=use_rag,
            abort_ctx=abort_ctx,
        )

    finally:
        if reader_task is not None and not reader_task.done():
            reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await reader_task
        await service.aclose()
        # Be polite: close if we haven't already.
        if ws.client_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await ws.close(code=WS_CLOSE_NORMAL)


async def _stream_reply(
    ws: WebSocket,
    *,
    service: ChatService,
    session_uuid: uuid.UUID,
    content: str,
    use_rag: bool,
    abort_ctx: AbortContext,
) -> None:
    """Run :meth:`ChatService.generate` and push each event over the socket."""

    try:
        async for raw in service.generate(
            str(session_uuid),
            content,
            use_rag=use_rag,
            abort=abort_ctx,
        ):
            try:
                event = coerce_event(raw)
            except Exception:
                logger.warning("dropping malformed event: %r", raw)
                event = ErrorEvent(code="PROTOCOL", message="malformed event")
            await _safe_send(ws, event.model_dump())
    except Exception as exc:
        logger.exception("chat_ws blew up mid-flight")
        await _safe_send(ws, ErrorEvent(code="INTERNAL", message=str(exc)).model_dump())


async def _safe_send(ws: WebSocket, payload: dict[str, object]) -> None:
    """Send JSON, swallowing the error if the peer already hung up."""
    if ws.client_state != WebSocketState.CONNECTED:
        return
    with contextlib.suppress(Exception):
        await ws.send_json(payload)
