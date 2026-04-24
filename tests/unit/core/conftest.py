"""Shared fakes + fixtures for ``core/`` unit tests.

Placed in ``conftest.py`` (not a regular module) so we don't need an
``__init__.py`` inside ``tests/unit/core/`` — that would shadow the real
``core`` package on ``sys.path``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from core.llm.client import ChatChunk, ChatMessage


class FakeLLM:
    """Deterministic in-memory :class:`~core.llm.client.LLMClient`."""

    def __init__(self, deltas: list[str] | None = None) -> None:
        self.deltas = deltas if deltas is not None else ["hello", " world"]
        self.seen: list[list[ChatMessage]] = []
        self.closed = False

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        del model
        self.seen.append(list(messages))
        for delta in self.deltas:
            yield ChatChunk(delta=delta, done=False)
        yield ChatChunk(delta="", done=True, usage={"eval_count": 42})

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        del model
        return [[float(len(t))] for t in texts]

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_llm_factory() -> type[FakeLLM]:
    """Expose :class:`FakeLLM` as a fixture so tests don't import it directly."""
    return FakeLLM
