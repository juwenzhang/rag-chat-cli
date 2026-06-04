"""Path-scoped CORS middleware.

Starlette's :class:`fastapi.middleware.cors.CORSMiddleware` is single-policy:
once installed it sees every request for the ASGI app it wraps, regardless
of which sub-app eventually owns the route. We need two policies:

* Strict origin allowlist on the legacy / browser surface
  (``/auth``, ``/chat``, …) so cookie-bearing cross-origin POSTs stay safe.
* Wide-open CORS on the ``/v1/*`` non-browser surface so the Ink CLI works
  through whatever reverse proxy / CDN sits in front.

This middleware delegates to a real ``CORSMiddleware`` instance only when
the path does **not** match an excluded prefix; everything else falls
through untouched and is handled by the sub-app's own middleware.

See ``docs/MULTI_CLIENT_AUTH_DESIGN.md`` Phase 1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware

if TYPE_CHECKING:
    from collections.abc import Iterable

    from starlette.types import ASGIApp, Receive, Scope, Send

__all__ = ["PathFilteredCORSMiddleware"]


class PathFilteredCORSMiddleware:
    """Wraps :class:`CORSMiddleware`, but bypasses listed path prefixes.

    The signature matches Starlette's ``_MiddlewareFactory`` protocol —
    callable as ``Middleware(app, **kwargs)`` returning an ASGI app — so
    ``app.add_middleware(PathFilteredCORSMiddleware, ...)`` works without
    any wrappers.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        excluded_prefixes: Iterable[str] = (),
        **cors_kwargs: object,
    ) -> None:
        self._excluded: tuple[str, ...] = tuple(excluded_prefixes)
        # The wrapped CORSMiddleware is built once and shared. CORSMiddleware
        # accepts a generous kwargs surface; we forward everything verbatim.
        self._cors = CORSMiddleware(app, **cors_kwargs)  # type: ignore[arg-type]
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        path = scope.get("path", "")
        if any(path.startswith(prefix) for prefix in self._excluded):
            # Skip the outer CORS — the sub-app installs its own wide-open
            # CORS for these prefixes.
            await self._app(scope, receive, send)
            return
        await self._cors(scope, receive, send)
