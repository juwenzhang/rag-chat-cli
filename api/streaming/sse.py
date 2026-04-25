"""SSE wire-format helpers.

We hand-roll the framing instead of pulling in ``sse-starlette`` — the spec
is ~20 lines and a dedicated dep would only blur the contract. Key rules:

* one frame per event, terminated by an **empty line** (``\\n\\n``);
* ``event: <type>`` line lets browsers filter by type client-side;
* ``data:`` lines **must not** contain raw newlines — pydantic's
  ``model_dump_json()`` is single-line, so we're safe;
* leading ``:`` is a comment line, used here for keepalive pings.

See AGENTS.md §5.3 for the event catalogue these frames carry.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from api.streaming.protocol import StreamEvent, event_adapter

__all__ = [
    "KEEPALIVE_FRAME",
    "event_to_sse",
    "merge_with_keepalive",
]


#: Sent every `interval` seconds while the event stream is idle. Starts with
#: ``:`` so browser EventSource clients treat it as a comment and ignore it;
#: proxies (nginx, cloudfront) see traffic and keep the connection open.
KEEPALIVE_FRAME: bytes = b": keepalive\n\n"


def event_to_sse(event: StreamEvent) -> bytes:
    """Serialise a validated :data:`StreamEvent` into SSE wire bytes.

    The event's ``type`` (``"token"`` / ``"done"`` / …) is also emitted as
    the SSE ``event:`` tag so clients can route by name without parsing JSON
    first.
    """
    # model_dump_json -> always single line; safe to drop directly after `data:`.
    payload = event_adapter.dump_json(event).decode("utf-8")
    return f"event: {event.type}\ndata: {payload}\n\n".encode()


async def merge_with_keepalive(
    stream: AsyncIterator[bytes],
    *,
    interval: float = 15.0,
) -> AsyncIterator[bytes]:
    """Wrap ``stream`` and inject ``KEEPALIVE_FRAME`` after idle > ``interval``.

    Implementation notes:
    * We read the wrapped iterator via a background task so idleness is
      measured from "last yielded byte", not "last byte the LLM produced".
    * Cancellation-safe: if the consumer disconnects, the outer
      ``async for`` raises ``GeneratorExit`` → ``finally`` cancels the
      reader task cleanly.
    * ``StopAsyncIteration`` is turned into a sentinel because asyncio
      tasks do not natively propagate it — raising it from ``Task.result()``
      would be swallowed by the event loop.
    """

    _END = object()
    aiter = stream.__aiter__()
    pending: asyncio.Task[object] | None = None

    async def _next() -> object:
        try:
            return await aiter.__anext__()
        except StopAsyncIteration:
            return _END

    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(_next())
            try:
                chunk = await asyncio.wait_for(asyncio.shield(pending), timeout=interval)
            except asyncio.TimeoutError:
                yield KEEPALIVE_FRAME
                continue
            pending = None
            if chunk is _END:
                return
            assert isinstance(chunk, (bytes, bytearray))
            yield bytes(chunk)
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            # Any exception from a cancelled inner iterator is intentionally
            # swallowed — the consumer has already disconnected.
            with contextlib.suppress(BaseException):
                await pending
