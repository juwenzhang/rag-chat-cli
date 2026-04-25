"""Test doubles for API-layer suites.

Kept out of ``conftest.py`` so we can ``import tests.api._fakes`` from
dependency overrides without pulling in pytest's session machinery.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from core.llm.client import ChatChunk, ChatMessage


class FakeLLM:
    """Deterministic in-memory LLM that yields a scripted list of deltas.

    Matches :class:`core.llm.client.LLMClient` structurally.
    """

    def __init__(
        self,
        deltas: list[str] | None = None,
        *,
        per_token_delay: float = 0.0,
    ) -> None:
        self.deltas = deltas if deltas is not None else ["hello ", "world", "!"]
        self.per_token_delay = per_token_delay
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
            if self.per_token_delay:
                await asyncio.sleep(self.per_token_delay)
            yield ChatChunk(delta=delta, done=False)
        yield ChatChunk(delta="", done=True, usage={"eval_count": len(self.deltas)})

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
