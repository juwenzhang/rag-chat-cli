"""LLM provider-agnostic abstractions.

The goal is that :class:`core.chat_service.ChatService` can talk to any backend
(Ollama, vLLM, OpenAI-compatible, Anthropic, …) without knowing the transport.

P1.1 added tool-calling primitives (``ToolSpec`` / ``ToolCall``) and extended
``ChatMessage`` + ``ChatChunk`` with optional tool fields. The shape mirrors
the OpenAI / Ollama function-calling wire format because it is the most
explicit of the major contracts; adapters for Anthropic-style content blocks
should normalize *into* this shape.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

__all__ = [
    "ChatChunk",
    "ChatMessage",
    "LLMClient",
    "LLMError",
    "Role",
    "ToolCall",
    "ToolSpec",
]


Role = Literal["user", "assistant", "system", "tool"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One tool offered to the LLM.

    Mirrors the OpenAI / Ollama ``functions[i]`` / ``tools[i].function`` shape.
    ``parameters`` is a JSON-Schema dict describing the function's arguments.
    """

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool invocation requested by the assistant.

    ``id`` is the provider-assigned call id (or a synthesized one when the
    provider does not emit ids — needed so the matching ``role="tool"`` reply
    can reference back via ``ChatMessage.tool_call_id``).
    ``arguments`` is the JSON-decoded argument object; clients should round-trip
    it through ``json.dumps`` for providers that expect a string.
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One message on the wire to/from the LLM.

    Defaults preserve the pre-P1.1 shape: callers that only set ``role`` and
    ``content`` keep working unchanged. Tool-flavoured fields are populated
    only when the message participates in a tool call:

    * assistant turn that *requests* tool calls — set ``tool_calls``
    * tool result turn (``role="tool"``) — set ``tool_call_id`` (and
      typically a non-empty ``content`` containing the tool output)
    """

    role: Role
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ChatChunk:
    """One incremental piece of an assistant reply.

    ``done=True`` indicates the stream is over; ``delta`` may still be the
    empty string on the terminator chunk.

    ``tool_calls`` carries **finalized** tool calls — adapters should
    accumulate any per-call streaming deltas internally and only emit
    each call once when it is complete (either on a dedicated chunk or
    on the ``done`` chunk). This keeps the orchestrator (ReAct loop)
    simple: it acts on whole tool calls, not partial fragments.
    """

    delta: str = ""
    done: bool = False
    usage: dict[str, object] | None = None
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)


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

    ``tools`` may be ``None`` (no tools offered) or a list of :class:`ToolSpec`.
    Backends that do not support function calling MUST raise :class:`LLMError`
    when ``tools`` is non-empty rather than silently ignoring it.
    """

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        tools: list[ToolSpec] | None = None,
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
