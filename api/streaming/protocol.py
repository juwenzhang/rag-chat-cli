"""Pydantic v2 event schema shared by SSE / WebSocket / CLI.

Single source of truth: `api/routers/chat_stream.py`, `api/routers/chat_ws.py`
and `app/chat_app.py` all import `StreamEvent` + `coerce_event` from this
module. Any field change lands here and every transport inherits it.

P1.5 added the agent-loop events ``thought / tool_call / tool_result``
alongside the original ``retrieval / token / done / error``. The set is
otherwise stable. `TypeAdapter(StreamEvent)` validates dicts emitted by
:meth:`core.chat_service.ChatService.generate` into the concrete tagged-union
member — ChatService stays dependency-free by yielding plain dicts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

__all__ = [
    "DoneEvent",
    "ErrorEvent",
    "RetrievalEvent",
    "RetrievalHit",
    "StreamEvent",
    "ThoughtEvent",
    "TokenEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "coerce_event",
    "event_adapter",
]


class RetrievalHit(BaseModel):
    """One snippet surfaced by RAG retrieval."""

    model_config = ConfigDict(extra="ignore")

    document_id: str | None = None
    chunk_id: str | None = None
    title: str | None = None
    content: str
    score: float
    source: str | None = None


class RetrievalEvent(BaseModel):
    type: Literal["retrieval"] = "retrieval"
    hits: list[RetrievalHit]


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    delta: str


class ThoughtEvent(BaseModel):
    """Model reasoning content (e.g. ``<think>…</think>`` tags or provider-
    surfaced reasoning fields). Optional — only emitted by providers/models
    that expose explicit thinking."""

    type: Literal["thought"] = "thought"
    text: str


class ToolCallEvent(BaseModel):
    """The model has requested one tool call. Emitted *before* the host
    executes the tool — UI can render an "executing X(…)" indicator."""

    type: Literal["tool_call"] = "tool_call"
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]


class ToolResultEvent(BaseModel):
    """The host has executed the tool. ``content`` is the string fed back to
    the LLM as the ``role="tool"`` message; UI typically renders it inline."""

    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    tool_name: str
    content: str
    is_error: bool = False


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    message_id: str | None = None
    duration_ms: int | None = None
    usage: dict[str, Any] | None = None
    # The model + provider that actually produced the reply. Surfaced so the
    # UI can show ground-truth "this answer came from qwen2.5:7b on local-ollama"
    # in the message footer (and so users can verify a model switch took effect).
    model: str | None = None
    provider_name: str | None = None


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


#: Discriminated union so pydantic can pick the right concrete event from a
#: plain dict in O(1) on the ``type`` tag. ``Union`` (not ``|``) is used here
#: because ``Field(discriminator=...)`` needs the ``Annotated`` + ``Union``
#: combo to generate a proper OpenAPI oneOf/discriminator.
StreamEvent = Annotated[
    Union[  # noqa: UP007
        RetrievalEvent,
        TokenEvent,
        ThoughtEvent,
        ToolCallEvent,
        ToolResultEvent,
        DoneEvent,
        ErrorEvent,
    ],
    Field(discriminator="type"),
]

#: Module-level adapter so we don't pay the schema-building cost per event.
event_adapter: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)


def coerce_event(data: Mapping[str, Any]) -> StreamEvent:
    """Validate a plain dict/TypedDict into the concrete :data:`StreamEvent`.

    Accepts ``core.streaming.events.Event`` (TypedDict) as well as a raw
    dict — both are runtime-equivalent. Callers should prefer this over
    constructing the models by hand because :class:`ChatService` yields
    TypedDicts (intentionally: it must not depend on FastAPI / Pydantic
    models).
    """
    return event_adapter.validate_python(data)
