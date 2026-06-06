"""Session cookie helpers (P-AUTH-2).

Browsers authenticate via two HttpOnly cookies on the legacy ``/``
surface:

* ``rag_at`` — the access JWT. ``Path=/`` so every request carries it.
* ``rag_rt`` — the refresh JWT. ``Path=/auth`` so it never leaks on
  regular reads; the only paths that can see it are ``/auth/refresh``
  and ``/auth/logout``. ``SameSite=Strict`` regardless of the
  ``cookie_samesite`` setting so a cross-site GET cannot smuggle it.

The CLI / ``/v1/*`` surface ignores these helpers entirely — that
surface is Bearer-only by design (see ``api/app.py``).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from service.auth.service import TokenPair as DomainTokenPair

if TYPE_CHECKING:
    from fastapi import Response

__all__ = [
    "REFRESH_COOKIE_PATH",
    "clear_session_cookies",
    "set_session_cookies",
]

# Refresh cookie is restricted to ``/auth`` so regular API reads cannot
# observe it. Aligns with browser-side ``proxy.ts`` expectations and the
# ``MULTI_CLIENT_AUTH_DESIGN`` boundary (this only applies to the legacy
# ``/`` surface, not ``/v1/*``).
REFRESH_COOKIE_PATH = "/auth"


def _max_age_seconds(expires_at: datetime) -> int:
    """Number of seconds from "now" to ``expires_at``, clamped to ≥ 0."""
    delta = expires_at - datetime.now(tz=timezone.utc)
    return max(0, int(delta.total_seconds()))


def set_session_cookies(response: Response, pair: DomainTokenPair) -> None:
    """Write ``rag_at`` + ``rag_rt`` onto ``response``.

    Reads cookie names / Secure flag / SameSite / Domain from
    :data:`settings.settings.auth` so deployment-time tuning needs zero
    code changes. The refresh cookie always uses ``Strict`` SameSite
    even when the global setting is ``Lax`` — there's no legitimate
    cross-site request that should ship a refresh token.
    """
    from settings import settings

    cfg = settings.auth
    secure = cfg.cookie_secure
    samesite_at: Literal["lax", "strict", "none"] = cfg.cookie_samesite
    samesite_rt: Literal["lax", "strict", "none"] = "strict"
    domain = cfg.cookie_domain or None

    response.set_cookie(
        key=cfg.cookie_access_name,
        value=pair.access_token,
        max_age=_max_age_seconds(pair.access_expires_at),
        path="/",
        domain=domain,
        secure=secure,
        httponly=True,
        samesite=samesite_at,
    )
    response.set_cookie(
        key=cfg.cookie_refresh_name,
        value=pair.refresh_token,
        max_age=_max_age_seconds(pair.refresh_expires_at),
        path=REFRESH_COOKIE_PATH,
        domain=domain,
        secure=secure,
        httponly=True,
        samesite=samesite_rt,
    )


def clear_session_cookies(response: Response) -> None:
    """Wipe ``rag_at`` + ``rag_rt``. Mirror of :func:`set_session_cookies`.

    Browsers honour cookie deletion only when the ``Path`` and ``Domain``
    match the original Set-Cookie, so we re-emit both with ``Max-Age=0``
    using the exact attributes used at write time.
    """
    from settings import settings

    cfg = settings.auth
    domain = cfg.cookie_domain or None

    response.delete_cookie(
        key=cfg.cookie_access_name,
        path="/",
        domain=domain,
    )
    response.delete_cookie(
        key=cfg.cookie_refresh_name,
        path=REFRESH_COOKIE_PATH,
        domain=domain,
    )
