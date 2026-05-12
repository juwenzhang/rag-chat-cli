"""Canonical streaming event shape.

Single source of truth for the event dicts that flow from
:meth:`core.chat_service.ChatService.generate` to every consumer
(:class:`ui.chat_view.ChatView`, the SSE/WS routers in :mod:`api`).

Event vocabulary (each ``type`` value uses a disjoint subset of fields):

============  =================================================================
type          fields
============  =================================================================
user_message  ``message_id``
retrieval     ``hits``
token         ``delta``
thought       ``text``  *(P1.5 — model "thinking" content)*
tool_call     ``tool_call_id``, ``tool_name``, ``arguments``  *(P1.5)*
tool_result   ``tool_call_id``, ``tool_name``, ``content``, ``is_error``  *(P1.5)*
done          ``message_id``, ``duration_ms``, ``usage``
error         ``code``, ``message``
ping / pong   *(heartbeat only)*
============  =================================================================

Backward compatibility: P1.5 additions are purely *additive*. Pre-P1.5
consumers that don't know ``thought / tool_call / tool_result`` should
ignore unknown ``type`` values rather than fail; the pydantic
:data:`api.streaming.protocol.StreamEvent` union likewise just gains new
members.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

__all__ = ["Event", "EventType"]


EventType = Literal[
    "user_message",
    "retrieval",
    "token",
    "thought",
    "tool_call",
    "tool_result",
    "done",
    "error",
    "ping",
    "pong",
]


class Event(TypedDict, total=False):
    """Streaming event dict. ``total=False`` — every field optional; presence
    depends on the discriminator ``type``. See module docstring for the
    field-set per ``type``."""

    type: EventType
    # token / done / error / retrieval — pre-P1.5
    delta: str
    hits: list[dict[str, Any]]
    message_id: str
    usage: dict[str, Any]
    duration_ms: int
    code: str
    message: str
    # thought — P1.5
    text: str
    # tool_call / tool_result — P1.5
    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    content: str
    is_error: bool
