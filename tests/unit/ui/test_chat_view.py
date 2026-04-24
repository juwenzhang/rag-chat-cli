"""ChatView streaming smoke test — uses an in-memory Console."""

from __future__ import annotations

import io
from collections.abc import AsyncIterator

import pytest
from rich.console import Console

from ui.chat_view import ChatView, Event


async def _events() -> AsyncIterator[Event]:
    yield Event(type="token", delta="hello ")
    yield Event(type="token", delta="world")
    yield Event(type="done", duration_ms=42)


@pytest.mark.asyncio
async def test_stream_assistant_returns_full_text() -> None:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=80)
    view = ChatView(console)
    full = await view.stream_assistant(_events())
    assert full == "hello world"


def test_banner_prints_model_name() -> None:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=80)
    ChatView(console).banner("qwen2.5:1.5b")
    out = buf.getvalue()
    assert "rag-chat" in out and "qwen2.5:1.5b" in out and "ready" in out
