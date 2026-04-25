"""``/auth`` routes — register / login / refresh / logout.

Every endpoint is a one-liner that delegates to :class:`AuthService`. Errors
raised by the service propagate up to :mod:`api.middleware.errors` which
maps them to JSON responses.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from api.deps import get_auth_service
from api.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenPair, UserOut
from core.auth.service import AuthService
from core.auth.service import TokenPair as DomainTokenPair

__all__ = ["router"]

router = APIRouter(tags=["auth"])


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
    svc: AuthService = Depends(get_auth_service),
) -> TokenPair:
    pair = await svc.login(body.email, body.password)
    return _to_token_pair(pair)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate a refresh token",
)
async def refresh(
    body: RefreshIn,
    svc: AuthService = Depends(get_auth_service),
) -> TokenPair:
    pair = await svc.refresh(body.refresh_token)
    return _to_token_pair(pair)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the supplied refresh token",
)
async def logout(
    body: RefreshIn,
    svc: AuthService = Depends(get_auth_service),
) -> None:
    await svc.logout(body.refresh_token)
