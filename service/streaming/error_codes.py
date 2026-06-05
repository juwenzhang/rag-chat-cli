"""Single source of truth for SSE event types and error codes.

Splits into two enums to mirror the wire-protocol distinction:

* :class:`EventType` — the ``type`` discriminator on every SSE/WS frame.
* :class:`FlowErrorCode` — the ``code`` on ``error`` frames produced by
  :class:`service.chat.service.ChatService` itself (LLM-upstream codes
  live on :class:`service.llm.client.LLMError` subclasses).

Both subclass ``(str, Enum)`` (Python 3.10 compat) so ``EventType.TOKEN``
serialises to ``"token"`` transparently in dicts / JSON.

See ``docs/backend/STREAM_PROTOCOL.md`` and ``docs/backend/ERROR_CODES.md``.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["EventType", "FlowErrorCode", "TransportErrorCode"]


class EventType(str, Enum):
    """SSE / WebSocket event ``type`` discriminator."""

    USER_MESSAGE = "user_message"
    RETRIEVAL = "retrieval"
    TOKEN = "token"
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    DONE = "done"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class FlowErrorCode(str, Enum):
    """``code`` values emitted by :class:`ChatService.generate` itself.

    LLM-upstream codes (``llm_rate_limited`` etc.) are owned by
    :class:`service.llm.client.LLMError` subclasses, not this enum.
    """

    ABORTED = "ABORTED"
    RETRIEVAL_FAILED = "retrieval_failed"
    MEMORY_READ_FAILED = "memory_read_failed"
    MEMORY_WRITE_FAILED = "memory_write_failed"
    MAX_STEPS_REACHED = "max_steps_reached"
    UNEXPECTED = "unexpected"


class TransportErrorCode(str, Enum):
    """``code`` values emitted by the SSE / WebSocket transport layer.

    Used by routers when a frame fails schema validation (``PROTOCOL``)
    or an unhandled exception escapes ``ChatService`` (``INTERNAL``).
    """

    PROTOCOL = "PROTOCOL"
    INTERNAL = "INTERNAL"
