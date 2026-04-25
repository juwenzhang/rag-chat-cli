"""Unit tests for api.streaming.sse."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest


def test_event_to_sse_frame_shape() -> None:
    from api.streaming.protocol import TokenEvent
    from api.streaming.sse import event_to_sse

    frame = event_to_sse(TokenEvent(delta="hi"))
    text = frame.decode("utf-8")
    assert text.startswith("event: token\n")
    assert "\ndata: " in text
    assert text.endswith("\n\n")
    # data line must contain JSON on a single line.
    data_line = text.split("\ndata: ", 1)[1].split("\n\n", 1)[0]
    assert data_line.startswith("{") and data_line.endswith("}")
    assert "\n" not in data_line


async def _aiter_of(items: list[bytes], delay: float = 0.0) -> AsyncIterator[bytes]:
    for it in items:
        if delay:
            await asyncio.sleep(delay)
        yield it


@pytest.mark.anyio
async def test_merge_with_keepalive_passes_stream_through() -> None:
    from api.streaming.sse import merge_with_keepalive

    chunks = [b"a", b"b", b"c"]
    got = [c async for c in merge_with_keepalive(_aiter_of(chunks), interval=10.0)]
    assert got == chunks


@pytest.mark.anyio
async def test_merge_with_keepalive_injects_ping_on_idle() -> None:
    from api.streaming.sse import KEEPALIVE_FRAME, merge_with_keepalive

    async def _slow() -> AsyncIterator[bytes]:
        await asyncio.sleep(0.05)
        yield b"late"

    got: list[bytes] = []
    async for chunk in merge_with_keepalive(_slow(), interval=0.01):
        got.append(chunk)
        if chunk == b"late":
            break
    # Saw at least one keepalive before the real chunk.
    assert KEEPALIVE_FRAME in got
    assert got[-1] == b"late"


@pytest.mark.anyio
async def test_merge_with_keepalive_cancellable() -> None:
    """Consumer bails out → no leaked background task."""
    from api.streaming.sse import merge_with_keepalive

    async def _forever() -> AsyncIterator[bytes]:
        while True:
            await asyncio.sleep(1)
            yield b"x"

    merged = merge_with_keepalive(_forever(), interval=0.01)

    async def _consume_one_then_break() -> None:
        async for _ in merged:
            break  # immediate bailout

    # Should complete quickly without a traceback.
    await asyncio.wait_for(_consume_one_then_break(), timeout=0.5)
