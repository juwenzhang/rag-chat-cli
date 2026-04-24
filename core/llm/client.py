"""LLM provider-agnostic abstractions.

Design doc: ``openspec/changes/split-core-domain-layer/design.md`` §"core/llm/client.py".

The goal is that :class:`core.chat_service.ChatService` can talk to any backend
(Ollama today, vLLM / OpenAI tomorrow) without knowing the transport.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

__all__ = [
    "ChatChunk",
    "ChatMessage",
    "LLMClient",
    "LLMError",
]


Role = Literal["user", "assistant", "system"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One message on the wire to/from the LLM."""

    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class ChatChunk:
    """One incremental piece of an assistant reply.

    ``done=True`` indicates the stream is over; ``delta`` may still be the
    empty string on the terminator chunk.
    """

    delta: str
    done: bool = False
    usage: dict[str, object] | None = None


class LLMError(Exception):
    """Transport / protocol errors raised by any :class:`LLMClient`.

    Sub-classes may refine this (e.g. ``LLMConnectionError``) but callers
    should generally be able to ``except LLMError`` at the service boundary.
    """


@runtime_checkable
class LLMClient(Protocol):
    """Minimum contract every LLM backend must satisfy.

    Concrete clients are expected to be cheap to construct but may hold an
    ``httpx.AsyncClient`` internally; call :meth:`aclose` at shutdown.

    ``chat_stream`` is declared without ``async`` so it matches both
    ``async def ... yield`` async generators (as used by :class:`OllamaClient`)
    and coroutines returning an ``AsyncIterator``. ``embed`` / ``aclose`` are
    regular coroutines.
    """

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        """Stream an assistant reply token-by-token."""
        ...

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """Return an embedding vector for every input text."""
        ...

    async def aclose(self) -> None:
        """Release underlying network resources. Idempotent."""
        ...
