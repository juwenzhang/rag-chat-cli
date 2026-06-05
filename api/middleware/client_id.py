"""``X-Client-Id`` middleware — Phase 1 of multi-client auth.

See ``docs/backend/MULTI_CLIENT_AUTH_DESIGN.md`` for the full picture. The runtime
contract is short:

* Requests under ``/v1/*`` (the non-browser surface used by the Ink CLI and
  future mobile / IDE clients) MUST send an ``X-Client-Id`` header.
* The value MUST be in the configured allowlist
  (``settings.app.allowed_client_ids``). Unknown clients get a 400 — never a
  500 — so the error is obviously a config / packaging mistake instead of a
  server bug.
* Requests on legacy paths (``/auth``, ``/chat``, ``/me``, …) are untouched
  so the existing Next.js website keeps working with no changes.
* Successful identification is stashed on ``request.state.client_id`` so
  downstream code (logging, rate limiting, audit) can use it without
  re-parsing the header.

Pre-flight ``OPTIONS`` requests bypass the check — the browser hasn't sent
the actual request yet, so it cannot have set the header. CORS handles the
preflight separately.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from api.middleware.request_id import current_request_id
from api.schemas.common import ErrorResponse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable

    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

__all__ = ["ClientIdMiddleware"]

CLIENT_ID_HEADER = "X-Client-Id"


class ClientIdMiddleware(BaseHTTPMiddleware):
    """Require ``X-Client-Id`` for the ``/v1/*`` surface."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        protected_prefixes: Iterable[str] = ("/v1",),
        allowed_client_ids: Iterable[str] = (),
    ) -> None:
        super().__init__(app)
        # tuple for cheap startswith() match
        self._prefixes: tuple[str, ...] = tuple(protected_prefixes)
        self._allowed: frozenset[str] = frozenset(allowed_client_ids)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if not any(path.startswith(prefix) for prefix in self._prefixes):
            return await call_next(request)

        client_id = request.headers.get(CLIENT_ID_HEADER)
        if not client_id:
            return _error_response(
                status_code=400,
                code="MISSING_CLIENT_ID",
                message=f"{CLIENT_ID_HEADER} header is required for {self._prefixes[0]}/* paths",
            )

        if self._allowed and client_id not in self._allowed:
            # Don't leak the allowlist; the developer can correlate via the
            # request_id in their server logs.
            return _error_response(
                status_code=400,
                code="UNKNOWN_CLIENT_ID",
                message=f"{CLIENT_ID_HEADER} is not registered",
            )

        request.state.client_id = client_id
        return await call_next(request)


def _error_response(*, status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(
        code=code,
        message=message,
        request_id=current_request_id() or None,
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))
