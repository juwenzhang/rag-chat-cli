"""``/auth`` routes — register / login / refresh / logout.

Every endpoint delegates to :class:`AuthService` for business logic.
Errors raised by the service propagate up to :mod:`api.middleware.errors`
which maps them to JSON responses.

P-AUTH-2 cookie support
~~~~~~~~~~~~~~~~~~~~~~~
The browser surface (``/`` mount) authenticates via two HttpOnly cookies
issued by ``set_session_cookies`` (see :mod:`api.cookies`). Behaviour:

* ``login`` / ``register`` / ``refresh``: emit ``Set-Cookie`` whenever
  the caller opts in via ``?cookie=true``. The response body still
  carries the token pair so existing CLI / Bearer clients keep working
  unchanged.
* ``refresh``: the refresh token may be supplied either in the JSON
  body (CLI) **or** via the ``rag_rt`` cookie (browser). If both are
  present the body wins so a malicious cookie cannot override an
  intentional CLI request.
* ``logout``: clears the cookies in addition to revoking the JTI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from api.cookies import clear_session_cookies, set_session_cookies
from api.deps import get_auth_service
from api.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenPair, UserOut
from service.auth.errors import TokenInvalidError
from service.auth.service import AuthService
from service.auth.service import TokenPair as DomainTokenPair

__all__ = ["router"]

router = APIRouter(tags=["auth"])

# Reusable Query annotation so the same opt-in flag has identical docs
# on every endpoint that supports it.
_CookieOptIn = Annotated[
    bool,
    Query(
        alias="cookie",
        description=(
            "When true, the server also writes the session as HttpOnly "
            "cookies (``rag_at`` + ``rag_rt``). Browsers should set this; "
            "the CLI / non-browser clients leave it false (default) and "
            "rely on the body token pair."
        ),
    ),
]


def _to_token_pair(pair: DomainTokenPair) -> TokenPair:
    """Convert the dataclass returned by AuthService into the DTO.

    ``token_type`` on the DTO is typed ``Literal["bearer"]``; the domain
    dataclass stores a plain ``str`` but in practice only ever uses the
    literal ``"bearer"``, so we drop it from the kwargs and let the default
    kick in.
    """
    return TokenPair(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        access_expires_at=_ensure_utc(pair.access_expires_at),
        refresh_expires_at=_ensure_utc(pair.refresh_expires_at),
    )


def _ensure_utc(dt: datetime) -> datetime:
    """Refresh tokens are minted with UTC tz; be defensive for tests anyway."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _maybe_set_cookies(
    response: Response,
    pair: DomainTokenPair,
    *,
    opt_in: bool,
) -> None:
    """Write session cookies only when the caller opts in.

    Pulled out so every emitting endpoint shares one implementation.
    """
    if opt_in:
        set_session_cookies(response, pair)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user",
)
async def register(
    body: RegisterIn,
    svc: AuthService = Depends(get_auth_service),
) -> UserOut:
    user = await svc.register(body.email, body.password, display_name=body.display_name)
    return UserOut.model_validate(user)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Exchange email + password for a JWT pair",
)
async def login(
    body: LoginIn,
    response: Response,
    cookie: _CookieOptIn = False,
    svc: AuthService = Depends(get_auth_service),
) -> TokenPair:
    pair = await svc.login(body.email, body.password)
    _maybe_set_cookies(response, pair, opt_in=cookie)
    return _to_token_pair(pair)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate a refresh token",
)
async def refresh(
    request: Request,
    response: Response,
    body: RefreshIn | None = None,
    cookie: _CookieOptIn = False,
    svc: AuthService = Depends(get_auth_service),
) -> TokenPair:
    """Rotate the refresh token.

    Accepts the token from either the JSON body (CLI / Bearer flow) or
    the ``rag_rt`` cookie (browser). If neither is present we raise
    :class:`TokenInvalidError` so the caller gets the standard error
    envelope rather than an unhelpful 422.
    """
    from settings import settings

    refresh_token: str | None
    if body is not None and body.refresh_token:
        refresh_token = body.refresh_token
    else:
        refresh_token = request.cookies.get(settings.auth.cookie_refresh_name)

    if not refresh_token:
        raise TokenInvalidError("missing refresh token")

    pair = await svc.refresh(refresh_token)
    # Rotate cookies whenever the caller opts in OR the request came in
    # via a cookie — either way they expect the new pair to land back
    # in the same place. Falling back to the latter keeps the browser
    # path simple: it never has to add ``?cookie=true`` to refresh.
    cookie_was_used = bool(request.cookies.get(settings.auth.cookie_refresh_name))
    _maybe_set_cookies(response, pair, opt_in=cookie or cookie_was_used)
    return _to_token_pair(pair)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the supplied refresh token",
)
async def logout(
    request: Request,
    response: Response,
    body: RefreshIn | None = None,
    svc: AuthService = Depends(get_auth_service),
) -> None:
    """Revoke the refresh token AND wipe the session cookies.

    Like ``/refresh``, the refresh token may come from the body or the
    cookie. Cookies are always cleared regardless of which source was
    used so the browser can never be left with a half-removed session.
    """
    from settings import settings

    refresh_token: str | None
    if body is not None and body.refresh_token:
        refresh_token = body.refresh_token
    else:
        refresh_token = request.cookies.get(settings.auth.cookie_refresh_name)

    if refresh_token:
        await svc.logout(refresh_token)

    # Always clear cookies — even if the token was missing or the JTI
    # had already been revoked. A clean response means the browser
    # leaves the page in a known logged-out state.
    clear_session_cookies(response)
