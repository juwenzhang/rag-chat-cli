"""JWT encoding / decoding (AGENTS.md §6).

Pure, stateless helpers — do **not** touch the database here. The caller is
responsible for persisting the ``jti`` of refresh tokens to the
``refresh_tokens`` table (see :mod:`core.auth.service`).

Access tokens are fully stateless; refresh tokens are stateless on the wire
but their ``jti`` is checked against the DB on every use (for rotation +
reuse detection).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, cast

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from core.auth.errors import TokenExpiredError, TokenInvalidError

__all__ = [
    "TokenPayload",
    "TokenType",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
]

TokenType = Literal["access", "refresh"]


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """Decoded JWT payload (subset of claims we actually rely on).

    ``iat`` / ``exp`` are Unix seconds as stored in the JWT spec.
    """

    sub: str
    jti: str
    type: TokenType
    iat: int
    exp: int


def _now() -> datetime:
    """UTC now — separated so tests can monkeypatch easily."""
    return datetime.now(tz=timezone.utc)


def _encode(payload: dict[str, Any]) -> str:
    # Late import avoids forcing settings to load just for `import core.auth.tokens`.
    from settings import settings

    return str(
        jwt.encode(
            payload,
            settings.auth.jwt_secret,
            algorithm=settings.auth.jwt_alg,
        )
    )


def _build_payload(
    *,
    user_id: str,
    token_type: TokenType,
    expires_at: datetime,
    issued_at: datetime,
    jti: str,
) -> dict[str, Any]:
    return {
        "sub": user_id,
        "jti": jti,
        "type": token_type,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }


def create_access_token(
    user_id: uuid.UUID | str,
    *,
    ttl_min: int | None = None,
) -> str:
    """Sign an access token for ``user_id``. Default TTL from settings."""
    from settings import settings

    ttl = ttl_min if ttl_min is not None else settings.auth.access_token_ttl_min
    issued = _now()
    payload = _build_payload(
        user_id=str(user_id),
        token_type="access",
        expires_at=issued + timedelta(minutes=ttl),
        issued_at=issued,
        jti=uuid.uuid4().hex,
    )
    return _encode(payload)


def create_refresh_token(
    user_id: uuid.UUID | str,
    *,
    ttl_day: int | None = None,
) -> tuple[str, str]:
    """Sign a refresh token. Returns ``(jwt_string, jti)``; caller persists ``jti``."""
    from settings import settings

    ttl = ttl_day if ttl_day is not None else settings.auth.refresh_token_ttl_day
    issued = _now()
    jti = uuid.uuid4().hex
    payload = _build_payload(
        user_id=str(user_id),
        token_type="refresh",
        expires_at=issued + timedelta(days=ttl),
        issued_at=issued,
        jti=jti,
    )
    return _encode(payload), jti


def decode_token(token: str, *, expected_type: TokenType) -> TokenPayload:
    """Validate signature + expiry + type, return typed payload.

    Raises:
        TokenExpiredError: ``exp`` is in the past.
        TokenInvalidError: signature mismatch, malformed, or wrong ``type``.
    """
    from settings import settings

    try:
        raw = jwt.decode(
            token,
            settings.auth.jwt_secret,
            algorithms=[settings.auth.jwt_alg],
        )
    except ExpiredSignatureError as exc:
        raise TokenExpiredError("token expired") from exc
    except JWTError as exc:
        raise TokenInvalidError("invalid token") from exc

    raw_dict = cast("dict[str, Any]", raw)
    try:
        payload = TokenPayload(
            sub=str(raw_dict["sub"]),
            jti=str(raw_dict["jti"]),
            type=cast("TokenType", raw_dict["type"]),
            iat=int(raw_dict["iat"]),
            exp=int(raw_dict["exp"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenInvalidError("malformed token payload") from exc

    if payload.type != expected_type:
        raise TokenInvalidError(f"expected {expected_type} token, got {payload.type}")
    return payload
