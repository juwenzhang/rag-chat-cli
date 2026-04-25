"""Pydantic v2 event schema shared by SSE / WebSocket / CLI (AGENTS.md §5.3).

Single source of truth: `api/routers/chat_stream.py`, `api/routers/chat_ws.py`
and `app/chat_app.py` all import `StreamEvent` + `coerce_event` from this
module. Any field change lands here and every transport inherits it.

The four events match AGENTS.md §5.3 1:1. `TypeAdapter(StreamEvent)` is used
to validate dicts emitted by :class:`core.chat_service.ChatService.generate`
into the concrete tagged-union member — because ChatService still yields
plain dicts to stay dependency-free.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

__all__ = [
    "DoneEvent",
    "ErrorEvent",
    "RetrievalEvent",
    "RetrievalHit",
    "StreamEvent",
    "TokenEvent",
    "coerce_event",
    "event_adapter",
]


class RetrievalHit(BaseModel):
    """One snippet surfaced by RAG retrieval (AGENTS.md §5.3)."""

    model_config = ConfigDict(extra="ignore")

    # Source field name is ``content`` inside :class:`core.knowledge.base.KnowledgeHit`,
    # but the wire name is ``snippet`` per AGENTS.md. The router does the rename
    # when it builds the event dict; this schema is therefore stable on the wire.
    document_id: str | None = None
    title: str | None = None
    snippet: str
    score: float
    source: str | None = None


class RetrievalEvent(BaseModel):
    type: Literal["retrieval"] = "retrieval"
    hits: list[RetrievalHit]


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    delta: str


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    message_id: str | None = None
    duration_ms: int | None = None
    usage: dict[str, Any] | None = None


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str


#: Discriminated union so pydantic can pick the right concrete event from a
#: plain dict in O(1) on the ``type`` tag. ``Union`` (not ``|``) is used here
#: because ``Field(discriminator=...)`` needs the ``Annotated`` + ``Union``
#: combo to generate a proper OpenAPI oneOf/discriminator.
StreamEvent = Annotated[
    Union[RetrievalEvent, TokenEvent, DoneEvent, ErrorEvent],  # noqa: UP007
    Field(discriminator="type"),
]

#: Module-level adapter so we don't pay the schema-building cost per event.
event_adapter: TypeAdapter[StreamEvent] = TypeAdapter(StreamEvent)


def coerce_event(data: dict[str, Any]) -> StreamEvent:
    """Validate a plain dict into the concrete :data:`StreamEvent` member.

    Callers should prefer this over constructing the models by hand because
    :class:`ChatService` currently yields dicts (intentionally: it must not
    depend on FastAPI / Pydantic models).
    """
    return event_adapter.validate_python(data)
