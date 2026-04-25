"""Access log middleware — one structured log line per request.

Writes through stdlib :mod:`logging` so it picks up whatever formatter the
host process configured (the CLI uses ``utils.logger``; container runs can
swap in a JSON formatter). The line shape is deliberately stable so log
pipelines can parse it without regex acrobatics.

Noisy diagnostic routes (``/health``, ``/docs``, ``/openapi.json``) are
skipped to avoid drowning the signal.

**Secret scrubbing**: SSE's ``EventSource`` can't attach an
``Authorization`` header, so browsers authenticate by putting the JWT on
the query string (``?token=...``). We must **never** let raw tokens land
in the access log — :func:`_sanitize_query` rewrites them to ``***`` before
we format the line.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlencode

from starlette.middleware.base import BaseHTTPMiddleware

from api.middleware.request_id import current_request_id

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

__all__ = ["AccessLogMiddleware"]


_SKIP_PATHS: frozenset[str] = frozenset({"/health", "/docs", "/openapi.json", "/redoc"})

#: Keys whose values must be masked in logged URLs. Case-insensitive.
_SECRET_KEYS: frozenset[str] = frozenset(
    {"token", "access_token", "refresh_token", "jwt", "password"}
)
_REDACTED: str = "***"


def _sanitize_query(query: str) -> str:
    """Return ``query`` with any secret-valued key rewritten to ``***``.

    Preserves order and duplicate keys; non-secret values pass through
    unchanged so the log line stays useful for debugging real issues.
    """
    if not query:
        return ""
    pairs = parse_qsl(query, keep_blank_values=True)
    if not any(k.lower() in _SECRET_KEYS for k, _ in pairs):
        return query  # nothing to redact, avoid re-encoding
    scrubbed = [(k, _REDACTED if k.lower() in _SECRET_KEYS else v) for k, v in pairs]
    return urlencode(scrubbed, doseq=True)


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Emit ``access`` log records with method / path / status / duration."""

    def __init__(self, app: ASGIApp, *, logger_name: str = "api.access") -> None:
        super().__init__(app)
        self._logger = logging.getLogger(logger_name)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        started = time.monotonic()
        status = 500  # default if call_next blows up before response
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            safe_query = _sanitize_query(request.url.query)
            self._logger.info(
                "access method=%s path=%s query=%s status=%d duration_ms=%d request_id=%s",
                request.method,
                request.url.path,
                safe_query or "-",
                status,
                duration_ms,
                current_request_id() or "-",
            )
        return response
