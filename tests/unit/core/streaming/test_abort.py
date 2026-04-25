"""Unit tests for core.streaming.abort."""

from __future__ import annotations


def test_abort_starts_unset() -> None:
    from core.streaming.abort import AbortContext

    ctx = AbortContext()
    assert ctx.aborted is False


def test_abort_is_idempotent() -> None:
    from core.streaming.abort import AbortContext

    ctx = AbortContext()
    ctx.abort()
    ctx.abort()
    ctx.abort()
    assert ctx.aborted is True


async def test_wait_returns_after_abort() -> None:
    import asyncio

    from core.streaming.abort import AbortContext

    ctx = AbortContext()

    async def _abort_soon() -> None:
        await asyncio.sleep(0.01)
        ctx.abort()

    task = asyncio.create_task(_abort_soon())
    try:
        await asyncio.wait_for(ctx.wait(), timeout=1.0)
    finally:
        await task
    assert ctx.aborted is True
