"""FastAPI dependency helpers.

Keep this module import-light: heavier factories (like :class:`ChatService`)
live behind lazy imports so the ``api`` package can be imported from test
harnesses that don't need the full LLM stack.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.auth.errors import (
    AuthError,
    TokenExpiredError,
    TokenInvalidError,
    UserNotActiveError,
)
from core.auth.service import AuthService
from core.auth.tokens import decode_token
from db.models import User
from db.session import current_session_factory, get_session

if TYPE_CHECKING:
    from fastapi import WebSocket

__all__ = [
    "authenticate_ws",
    "get_auth_service",
    "get_current_user",
    "get_db_session",
    "get_session_factory",
]


_bearer = HTTPBearer(auto_error=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency wrapper around :func:`db.session.get_session`.

    Re-exported with a stable name so test overrides can target it directly.
    """
    async for session in get_session():
        yield session


def get_auth_service() -> AuthService:
    """Build an :class:`AuthService` bound to the module-level session factory."""
    return AuthService(current_session_factory())


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the module-level :class:`async_sessionmaker`.

    Exposed as a FastAPI dep so tests can ``app.dependency_overrides[get_session_factory]``
    to hand out a factory bound to an in-memory SQLite engine without poking
    :mod:`db.session` internals.
    """
    return current_session_factory()


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    """Resolve the ``Authorization: Bearer <jwt>`` header to a live user row.

    Raises an :class:`~fastapi.HTTPException` with the appropriate ``401``/
    ``403`` status so the global error handler can turn it into an
    :class:`api.schemas.common.ErrorResponse`.
    """
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    return await _resolve_user_from_access_token(creds.credentials, session)


async def _resolve_user_from_access_token(token: str, session: AsyncSession) -> User:
    """Shared JWT → User path for both HTTP and WebSocket entry points."""
    try:
        payload = decode_token(token, expected_type="access")
    except TokenExpiredError as exc:
        raise HTTPException(status_code=401, detail="token expired") from exc
    except TokenInvalidError as exc:
        raise HTTPException(status_code=401, detail="invalid token") from exc

    try:
        user_uuid = uuid.UUID(payload.sub)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="malformed subject") from exc

    user = await session.get(User, user_uuid)
    if user is None or not user.is_active:
        raise UserNotActiveError("user inactive or missing")
    return user


# ---------------------------------------------------------------------------
# WebSocket authentication
# ---------------------------------------------------------------------------

#: Custom WS close code for "auth failed". 4xxx is the private range
#: reserved by the WebSocket spec for application-level close codes.
WS_CLOSE_UNAUTHORIZED = 4401


async def authenticate_ws(ws: WebSocket) -> User | None:
    """Authenticate a WebSocket connection.

    Browsers can't set ``Authorization`` on ``new WebSocket(...)`` — they can
    only pass a *subprotocol* list or stuff the token into the query string.
    We accept both, in this order:

    1. ``Sec-WebSocket-Protocol: bearer, <token>`` — preferred; we echo
       ``"bearer"`` back as the accepted subprotocol so the handshake is clean.
    2. ``?token=<jwt>`` query parameter — fallback for pure-browser usage.

    On success the function returns a live :class:`User` and the socket is
    already :meth:`~WebSocket.accept`-ed. On failure it closes the socket with
    :data:`WS_CLOSE_UNAUTHORIZED` and returns ``None`` — callers should just
    ``return`` after that.
    """
    token, accept_subprotocol = _extract_ws_token(ws)
    if token is None:
        await ws.close(code=WS_CLOSE_UNAUTHORIZED, reason="missing bearer token")
        return None

    factory: async_sessionmaker[AsyncSession] = current_session_factory()
    try:
        async with factory() as session:
            user = await _resolve_user_from_access_token(token, session)
    except HTTPException:
        await ws.close(code=WS_CLOSE_UNAUTHORIZED, reason="invalid token")
        return None
    except AuthError:
        await ws.close(code=WS_CLOSE_UNAUTHORIZED, reason="user inactive")
        return None

    # Accept only now — prevents leaking "route exists but auth failed" to
    # clients that can't read the close reason. Pass back the bearer
    # subprotocol when that's how the client chose to authenticate.
    await ws.accept(subprotocol=accept_subprotocol)
    return user


def _extract_ws_token(ws: WebSocket) -> tuple[str | None, str | None]:
    """Return ``(token, accept_subprotocol)``.

    ``accept_subprotocol`` is ``"bearer"`` iff the client used the
    ``bearer, <token>`` subprotocol form; ``None`` otherwise.
    """
    # 1. Subprotocol header: "bearer, <token>" (comma-separated values).
    offered = ws.headers.get("sec-websocket-protocol") or ""
    parts = [p.strip() for p in offered.split(",") if p.strip()]
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1], "bearer"

    # 2. Query parameter fallback.
    q_token = ws.query_params.get("token")
    if q_token:
        return q_token, None

    return None, None
