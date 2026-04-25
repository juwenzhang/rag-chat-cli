"""Server-Sent Events endpoint for streaming chat (AGENTS.md §5.3).

One-way stream from server to client — the companion bidirectional variant
lives in :mod:`api.routers.chat_ws`. The two share the same event schema
(:mod:`api.streaming.protocol`) and are both backed by
:meth:`core.chat_service.ChatService.generate`.

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
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.chat_service import get_chat_service_for_user
from api.deps import get_current_user, get_db_session
from api.schemas.chat import MessageIn
from api.streaming.protocol import ErrorEvent, coerce_event
from api.streaming.sse import event_to_sse, merge_with_keepalive
from core.chat_service import ChatService
from db.models import ChatSession, User

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
                "Event types: `retrieval`, `token`, `done`, `error`. See AGENTS.md §5.3."
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

    async def _byte_stream() -> AsyncIterator[bytes]:
        try:
            async for raw_event in service.generate(
                str(body.session_id),
                body.content,
                use_rag=body.use_rag,
            ):
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
