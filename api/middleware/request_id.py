"""Request-ID middleware — propagates an ``X-Request-ID`` header.

Per AGENTS.md §7 the header name itself is configurable
(``settings.app.request_id_header``). The ID is echoed back on the response
and exposed in **two** places so downstream code can pick it up without
threading it through every call site:

1. ``request.state.request_id`` — survives across exceptions because the
   ``Request`` object itself is still alive when the global handler runs.
2. ``current_request_id()`` ContextVar — convenient when you don't have a
   handle to the request (e.g. inside a logging filter).

The ContextVar alone is **not** enough: ``BaseHTTPMiddleware`` runs the
downstream app in a sub-task, and our ``finally: ctx.reset(...)`` would
clear it before the FastAPI exception handler reads it.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

__all__ = ["RequestIDMiddleware", "current_request_id"]


_REQUEST_ID: ContextVar[str] = ContextVar("request_id", default="")


def current_request_id() -> str:
    """Return the current request ID or ``""`` outside of a request scope."""
    return _REQUEST_ID.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Ensure every response carries a stable request ID."""

    def __init__(self, app: ASGIApp, *, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rid = request.headers.get(self.header_name) or uuid.uuid4().hex
        # Stash on request.state so the exception handler can recover it
        # even when the downstream task already cleared the ContextVar.
        request.state.request_id = rid
        token = _REQUEST_ID.set(rid)
        try:
            response = await call_next(request)
        finally:
            _REQUEST_ID.reset(token)
        response.headers[self.header_name] = rid
        return response
