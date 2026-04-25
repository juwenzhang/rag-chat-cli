"""Centralised exception → :class:`ErrorResponse` mapping.

AGENTS.md §5 mandates a single JSON shape for every 4xx / 5xx. Routers MUST
NOT catch these exceptions themselves — raise the domain error, the handler
in this module picks the right HTTP status + short code.

Handlers deliberately keep ``message`` generic; details go into
``details`` and are omitted for auth errors to avoid leaking user-existence
information.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from api.middleware.request_id import current_request_id
from api.schemas.common import ErrorResponse
from core.auth.errors import (
    AuthError,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    TokenExpiredError,
    TokenInvalidError,
    TokenReuseError,
    UserNotActiveError,
)

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.requests import Request

__all__ = ["install_exception_handlers"]


logger = logging.getLogger(__name__)


def _resolve_request_id(request: Request | None) -> str | None:
    """Pull the request ID off ``request.state`` first, ContextVar second.

    ``BaseHTTPMiddleware`` runs the downstream app in a sub-task, and our
    :class:`RequestIDMiddleware` resets the ContextVar in ``finally``.
    By the time FastAPI's exception handler runs, the ContextVar is
    therefore empty. ``request.state.request_id`` is the durable copy.
    """
    if request is not None:
        rid = getattr(request.state, "request_id", "")
        if rid:
            return str(rid)
    # ContextVar fallback (covers code paths that don't have a Request, e.g.
    # background tasks). May still be empty in handler frames — see the
    # `request.state` doc above.
    fallback = current_request_id()
    return fallback or None


def _json(
    code: str,
    message: str,
    status: int,
    *,
    request: Request | None = None,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    rid = _resolve_request_id(request)
    body = ErrorResponse(
        code=code,
        message=message,
        request_id=rid,
        details=details,
    )
    response = JSONResponse(status_code=status, content=body.model_dump(mode="json"))
    # Echo the header on error paths too. RequestIDMiddleware sets it on the
    # happy path, but its `response.headers[...] = rid` line never runs when
    # the downstream raises — that's why we do it here as well.
    if rid:
        # Default header name; if the deployment customised it via
        # ``settings.app.request_id_header`` the middleware already wrote
        # *that* one on success. Setting both is harmless.
        response.headers.setdefault("X-Request-ID", rid)
    return response


# Map each concrete domain error to (status, code). Handler order matters for
# inheritance-based lookups, but using direct class keys keeps it O(1).
_AUTH_MAP: dict[type[AuthError], tuple[int, str]] = {
    InvalidCredentialsError: (401, "INVALID_CREDENTIALS"),
    EmailAlreadyExistsError: (409, "EMAIL_EXISTS"),
    TokenExpiredError: (401, "TOKEN_EXPIRED"),
    TokenInvalidError: (401, "TOKEN_INVALID"),
    TokenReuseError: (401, "TOKEN_REUSE_DETECTED"),
    UserNotActiveError: (403, "USER_INACTIVE"),
}


def install_exception_handlers(app: FastAPI) -> None:
    """Register every handler on ``app``.

    Safe to call multiple times: FastAPI just overwrites previous entries.
    """

    @app.exception_handler(AuthError)
    async def _handle_auth(request: Request, exc: AuthError) -> JSONResponse:
        status, code = _AUTH_MAP.get(type(exc), (401, "UNAUTHORIZED"))
        return _json(code, str(exc) or code.lower(), status, request=request)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic errors are safe to surface — they describe *client* input.
        return _json(
            "VALIDATION_ERROR",
            "request body failed validation",
            422,
            request=request,
            details={"errors": exc.errors()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Preserve any `detail` FastAPI / Starlette passed along.
        message = exc.detail if isinstance(exc.detail, str) else "http error"
        code = f"HTTP_{exc.status_code}"
        return _json(code, message, exc.status_code, request=request)

    @app.exception_handler(Exception)
    async def _handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        # 500 path must carry a full traceback to our logs so on-call can act.
        logger.exception("unhandled exception on %s %s", request.method, request.url.path)
        del exc  # avoid leaking repr(exc) to the client
        return _json("INTERNAL", "internal server error", 500, request=request)
