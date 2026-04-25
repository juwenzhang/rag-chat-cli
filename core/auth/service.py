"""AuthService — registration, login, refresh rotation, logout.

AGENTS.md §6:
* access tokens are stateless; refresh tokens are tracked via ``jti`` in the
  ``refresh_tokens`` table so we can revoke them.
* refresh rotation + reuse detection: an already-revoked refresh being
  presented again mass-revokes every live refresh for that user.

The service works directly against SQLAlchemy async sessions but **does not**
import FastAPI. It is therefore safe to consume from both the CLI and the
future API layer (Change 6).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select, update

from core.auth.errors import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    TokenInvalidError,
    TokenReuseError,
    UserNotActiveError,
)
from core.auth.password import hash_password, verify_password
from core.auth.tokens import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from db.models import RefreshToken, User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ["AuthService", "TokenPair"]


@dataclass(frozen=True, slots=True)
class TokenPair:
    """Fresh pair of (access, refresh) tokens + their expiry timestamps.

    The ``*_expires_at`` fields use UTC ``datetime`` objects — the API layer
    serialises them as ISO-8601 strings; the CLI stores them as-is in the
    local token file.
    """

    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    token_type: str = "bearer"


class AuthService:
    """Business entry point for every auth operation."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    async def register(
        self,
        email: str,
        password: str,
        *,
        display_name: str | None = None,
    ) -> User:
        """Create a new user. Raises :class:`EmailAlreadyExistsError` on conflict."""
        normalized = email.strip().lower()
        async with self._sf() as session:
            existing = await session.scalar(select(User).where(User.email == normalized))
            if existing is not None:
                raise EmailAlreadyExistsError("email already registered")

            user = User(
                email=normalized,
                hashed_password=hash_password(password),
                display_name=display_name,
                is_active=True,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    async def login(self, email: str, password: str) -> TokenPair:
        """Return a fresh :class:`TokenPair` or raise :class:`InvalidCredentialsError`."""
        normalized = email.strip().lower()
        async with self._sf() as session:
            user = await session.scalar(select(User).where(User.email == normalized))
            if user is None or not verify_password(password, user.hashed_password):
                # Identical error path for both branches to avoid enumeration.
                raise InvalidCredentialsError("invalid email or password")
            if not user.is_active:
                raise UserNotActiveError("user inactive")

            pair, jti, refresh_exp = self._issue_pair(user.id)
            session.add(
                RefreshToken(
                    user_id=user.id,
                    jti=jti,
                    expires_at=refresh_exp,
                )
            )
            await session.commit()
            return pair

    # ------------------------------------------------------------------
    # Refresh (rotation + reuse detection)
    # ------------------------------------------------------------------
    async def refresh(self, refresh_token: str) -> TokenPair:
        """Rotate a refresh token. Detects reuse and mass-revokes on abuse."""
        from settings import settings

        payload = decode_token(refresh_token, expected_type="refresh")
        try:
            user_uuid = uuid.UUID(payload.sub)
        except ValueError as exc:
            raise TokenInvalidError("malformed subject") from exc

        async with self._sf() as session:
            row = await session.scalar(select(RefreshToken).where(RefreshToken.jti == payload.jti))
            if row is None:
                raise TokenInvalidError("unknown refresh token")

            if row.revoked_at is not None:
                # Reuse detected — the presented token had already been rotated.
                if settings.auth.refresh_reuse_detection:
                    await session.execute(
                        update(RefreshToken)
                        .where(
                            RefreshToken.user_id == row.user_id,
                            RefreshToken.revoked_at.is_(None),
                        )
                        .values(revoked_at=_utcnow())
                    )
                    await session.commit()
                raise TokenReuseError("refresh token already used")

            user = await session.get(User, user_uuid)
            if user is None or not user.is_active:
                raise UserNotActiveError("user inactive")

            # Rotate: revoke current row, issue a new pair, persist new jti.
            row.revoked_at = _utcnow()
            pair, new_jti, refresh_exp = self._issue_pair(user.id)
            session.add(
                RefreshToken(
                    user_id=user.id,
                    jti=new_jti,
                    expires_at=refresh_exp,
                )
            )
            await session.commit()
            return pair

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------
    async def logout(self, refresh_token: str) -> None:
        """Revoke the supplied refresh token. No-op if it was already revoked."""
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except TokenInvalidError:
            # Caller may be logging out with a stale/corrupt token; swallow so
            # the CLI can still clean up its local file.
            return

        async with self._sf() as session:
            await session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.jti == payload.jti,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=_utcnow())
            )
            await session.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def get_user_by_access(self, access_token: str) -> User:
        """Resolve an access token back to a live user row."""
        payload = decode_token(access_token, expected_type="access")
        return await self._resolve_user(payload)

    async def _resolve_user(self, payload: TokenPayload) -> User:
        try:
            user_uuid = uuid.UUID(payload.sub)
        except ValueError as exc:
            raise TokenInvalidError("malformed subject") from exc

        async with self._sf() as session:
            user = await session.get(User, user_uuid)
        if user is None or not user.is_active:
            raise UserNotActiveError("user inactive")
        return user

    def _issue_pair(self, user_id: uuid.UUID) -> tuple[TokenPair, str, datetime]:
        """Mint a fresh token pair. Returns (pair, new_refresh_jti, refresh_exp)."""
        from settings import settings

        now = _utcnow()
        access = create_access_token(user_id)
        refresh, jti = create_refresh_token(user_id)
        access_exp = now + timedelta(minutes=settings.auth.access_token_ttl_min)
        refresh_exp = now + timedelta(days=settings.auth.refresh_token_ttl_day)
        pair = TokenPair(
            access_token=access,
            refresh_token=refresh,
            access_expires_at=access_exp,
            refresh_expires_at=refresh_exp,
        )
        return pair, jti, refresh_exp


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)
