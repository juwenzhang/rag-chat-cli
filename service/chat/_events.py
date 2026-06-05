"""Streaming-event builders shared across chat orchestration.

Lives next to :mod:`service.chat.service` so the chat orchestrator can
emit canonical ``error`` frames without duplicating dict-shape literals.
Both builders return :class:`service.core.streaming.events.Event` (TypedDict),
so callers get static field-name checking instead of free-form dicts.
"""

from __future__ import annotations

from service.core.streaming.error_codes import EventType, FlowErrorCode
from service.core.streaming.events import Event
from service.llm.client import LLMError

__all__ = ["aborted_event", "llm_error_event"]


def aborted_event() -> Event:
    """Canonical ``error`` frame for client-driven abort."""
    return {
        "type": EventType.ERROR.value,
        "code": FlowErrorCode.ABORTED.value,
        "message": "client aborted the stream",
    }


def llm_error_event(exc: LLMError) -> Event:
    """Surface an :class:`LLMError` as a structured ``error`` event.

    Carries ``code`` (subclass-specific, e.g. ``llm_rate_limited``) plus
    optional upstream context (``upstream_status``, ``upstream_url``,
    ``retry_after``) so the UI can render quota / paywall / auth prompts
    without text-matching the message. See ``docs/backend/ERROR_CODES.md``.
    """
    event: Event = {"type": EventType.ERROR.value, "code": exc.code, "message": str(exc)}
    if exc.upstream_status is not None:
        event["upstream_status"] = exc.upstream_status
    if exc.upstream_url is not None:
        event["upstream_url"] = exc.upstream_url
    if exc.retry_after is not None:
        event["retry_after"] = exc.retry_after
    return event
