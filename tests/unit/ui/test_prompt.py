"""SlashDispatcher routing tests."""

from __future__ import annotations

import pytest

from ui.prompt import SlashDispatcher


@pytest.mark.asyncio
async def test_dispatch_routes_to_handler_with_args() -> None:
    captured: list[list[str]] = []
    d = SlashDispatcher()
    d.register("foo", lambda args: captured.append(args))

    assert await d.dispatch("/foo a b") is True
    assert captured == [["a", "b"]]


@pytest.mark.asyncio
async def test_dispatch_ignores_non_slash() -> None:
    d = SlashDispatcher()
    d.register("foo", lambda args: None)
    assert await d.dispatch("hello world") is False


@pytest.mark.asyncio
async def test_dispatch_unknown_returns_false() -> None:
    d = SlashDispatcher()
    assert await d.dispatch("/nope") is False


@pytest.mark.asyncio
async def test_dispatch_supports_async_handler() -> None:
    seen: list[list[str]] = []

    async def handler(args: list[str]) -> None:
        seen.append(args)

    d = SlashDispatcher()
    d.register("async", handler)
    assert await d.dispatch("/async x") is True
    assert seen == [["x"]]
