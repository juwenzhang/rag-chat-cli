"""Cross-domain primitives shared by every service module.

Lives under ``service/core/`` (folded DDD layout, see
``docs/backend/SERVICE_LAYOUT.md`` §4): generic error types, observability
helpers, and the streaming protocol vocabulary. **No** imports from sibling
domain packages (``chat/``, ``knowledge/``, ``auth/``, …) — those depend on
``core``, never the reverse.

Re-exports the most-used symbols so callers can write
``from service.core import EventType, NotFoundError`` instead of digging
into submodules.
"""

from __future__ import annotations

from service.core.errors import ForbiddenError, NotFoundError
from service.core.streaming.error_codes import (
    EventType,
    FlowErrorCode,
    TransportErrorCode,
)

__all__ = [
    "EventType",
    "FlowErrorCode",
    "ForbiddenError",
    "NotFoundError",
    "TransportErrorCode",
]
