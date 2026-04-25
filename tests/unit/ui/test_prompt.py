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
async def test_dispatch_unknown_is_consumed_not_forwarded() -> None:
    """Unknown `/xxx` is swallowed (returns True) so the upstream loop never
    treats it as user prose — the prime defence against typos like
    `/ollama-ath sk-...` leaking secrets to the LLM."""
    d = SlashDispatcher()
    assert await d.dispatch("/nope") is True


@pytest.mark.asyncio
async def test_dispatch_unknown_invokes_callback_with_suggestion() -> None:
    seen: list[tuple[str, list[str]]] = []
    d = SlashDispatcher(on_unknown=lambda name, args: seen.append((name, args)))
    d.register("ollama-auth", lambda _a: None)

    assert await d.dispatch("/ollama-ath sk-secret") is True
    assert seen == [("ollama-ath", ["sk-secret"])]
    # And the suggestion engine offers the right correction.
    assert d.closest("ollama-ath") == ["ollama-auth"]


@pytest.mark.asyncio
async def test_dispatch_supports_async_handler() -> None:
    seen: list[list[str]] = []

    async def handler(args: list[str]) -> None:
        seen.append(args)

    d = SlashDispatcher()
    d.register("async", handler)
    assert await d.dispatch("/async x") is True
    assert seen == [["x"]]
