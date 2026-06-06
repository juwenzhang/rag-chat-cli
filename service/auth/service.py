"""AuthService — registration, login, refresh rotation, logout.

AGENTS.md §6:
* access tokens are stateless; refresh tokens are tracked via ``jti`` in the
  ``refresh_tokens`` table so we can revoke them.
* refresh rotation + reuse detection: an already-revoked refresh being
  presented again mass-revokes every live refresh for that user.

P-AUTH-2 (multi-provider login):
* credentials live in :class:`service.db.models.UserIdentity`, addressed
  by ``(provider, subject)``. ``AuthService`` orchestrates — actual
  identity CRUD lives in :class:`IdentityService`.
* ``users.hashed_password`` is kept populated as a read-only fallback
  during the transition window — see migration 0018 docstring. Reads go
  through :class:`IdentityService` which already encapsulates the
  fallback.

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

from service.auth.errors import (
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    TokenInvalidError,
    TokenReuseError,
    UserNotActiveError,
)
from service.auth.identities import IdentityService
from service.auth.password import hash_password
from service.auth.tokens import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from service.db.models import Org, OrgMember, RefreshToken, User

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
        self._identities = IdentityService()

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
        """Create a new user. Raises :class:`EmailAlreadyExistsError` on conflict.

        Writes both the new ``user_identities`` row (the source of truth
        going forward) AND the legacy ``users.hashed_password`` column.
        Keeping the legacy column populated lets us roll the service
        binary back to the pre-P-AUTH-2 version without losing access
        for newly-registered users — a cheap insurance policy for one
        release cycle. Future OAuth-only registrations will skip the
        legacy column entirely (it stays NULL for them).
        """
        normalized = email.strip().lower()
        hashed = hash_password(password)
        async with self._sf() as session:
            existing = await session.scalar(select(User).where(User.email == normalized))
            if existing is not None:
                raise EmailAlreadyExistsError("email already registered")

            user = User(
                email=normalized,
                # Legacy column — kept populated as a rollback safety net
                # while the wider codebase migrates to ``user_identities``.
                hashed_password=hashed,
                display_name=display_name,
                is_active=True,
            )
            session.add(user)
            # Flush so ``user.id`` is populated before we reference it
            # below for both the identity row and the personal-org
            # bootstrap.
            await session.flush()

            # Authoritative credential row.
            self._identities.attach(
                session,
                user_id=user.id,
                provider="password",
                subject=normalized,
                credential=hashed,
            )

            await self._bootstrap_user(session, user, display_name=display_name)

            await session.commit()
            await session.refresh(user)
            return user

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------
    async def login(self, email: str, password: str) -> TokenPair:
        """Return a fresh :class:`TokenPair` or raise :class:`InvalidCredentialsError`.

        Resolves the credential through :class:`IdentityService` so the
        password-vs-OTP split (later, P-AUTH-3) doesn't require touching
        this method again.
        """
        normalized = email.strip().lower()
        async with self._sf() as session:
            user = await self._identities.verify_password_credentials(
                session,
                email=normalized,
                password=password,
            )
            if user is None:
                # Identical error path for "no such user" and "wrong
                # password" — avoids account enumeration.
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
    # Shared post-registration bootstrap (used by every login provider)
    # ------------------------------------------------------------------
    async def _bootstrap_user(
        self,
        session: AsyncSession,
        user: User,
        *,
        display_name: str | None,
    ) -> None:
        """Create the personal org + initial membership for ``user``.

        Pulled out so future provider-specific registration paths
        (email-OTP, GitHub, …) don't duplicate the workspace setup.

        Caller is responsible for committing the transaction.
        """
        # Slug is ``personal-<12 hex>`` derived from the user's UUID so
        # it's collision-free without an extra round-trip. The org is
        # marked ``is_personal=True`` so the API refuses delete on it
        # — users can't accidentally orphan their default space.
        slug = "personal-" + user.id.hex[:12]
        normalized_email = user.email
        org_name = (display_name or normalized_email.split("@", 1)[0]) + "'s workspace"
        org = Org(
            slug=slug,
            name=org_name,
            owner_id=user.id,
            is_personal=True,
        )
        session.add(org)
        await session.flush()
        session.add(OrgMember(org_id=org.id, user_id=user.id, role="owner"))
        # No default wiki — the user creates wikis explicitly. The
        # ``wikis`` schema is in place but a fresh workspace lands empty
        # so RAG / knowledge-base scoping stays intentional.

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
