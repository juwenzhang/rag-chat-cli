"""IdentityService — pluggable login methods.

Splits "who you are" (``users``) from "how you proved it"
(``user_identities``) so registering a new login provider (email-OTP,
GitHub OAuth, …) does not require touching the core ``users`` schema.

This module deliberately stays free of FastAPI imports so it remains
usable from the CLI bootstrap path as well.

Design notes
~~~~~~~~~~~~
* :class:`IdentityService` is **stateless**: every public method takes
  the :class:`AsyncSession` it should use, leaving transaction control
  to the caller (typically :class:`service.auth.service.AuthService`).
  This keeps the unit-of-work boundary explicit and avoids spinning up
  a fresh session inside a session that the caller already owns.

* During the P-AUTH-2 transition we keep ``users.hashed_password``
  populated as a read-only fallback — see migration 0018 docstring.
  :meth:`IdentityService.verify_password_credentials` therefore checks
  the new table first and silently falls back to the legacy column,
  forwarding through a one-time backfill so the user converges to the
  new model on their next successful login.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy import select

from service.auth.password import hash_password, verify_password
from service.db.models import User, UserIdentity

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["PROVIDER_PASSWORD", "IdentityService"]


# Canonical provider name for the email + bcrypt login mechanism. Not a
# password literal — labelled to silence the ``S105`` heuristic.
PROVIDER_PASSWORD: Final[str] = "password"  # noqa: S105 — provider label, not a credential


class IdentityService:
    """CRUD-style helpers around :class:`UserIdentity`."""

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    async def find(
        self,
        session: AsyncSession,
        *,
        provider: str,
        subject: str,
    ) -> UserIdentity | None:
        """Return the identity row for ``(provider, subject)`` or ``None``."""
        row: UserIdentity | None = await session.scalar(
            select(UserIdentity).where(
                UserIdentity.provider == provider,
                UserIdentity.subject == subject,
            )
        )
        return row

    async def list_for_user(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
    ) -> list[UserIdentity]:
        """Every identity row attached to a user (used by future settings UI)."""
        result = await session.scalars(select(UserIdentity).where(UserIdentity.user_id == user_id))
        return list(result)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def attach(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        provider: str,
        subject: str,
        credential: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> UserIdentity:
        """Add a fresh identity row.

        Caller must commit. Raises a SQL ``IntegrityError`` if the
        ``(provider, subject)`` pair is already taken — handle that at
        the AuthService layer with a domain-specific error.
        """
        identity = UserIdentity(
            user_id=user_id,
            provider=provider,
            subject=subject,
            credential=credential,
            identity_metadata=metadata,
        )
        session.add(identity)
        return identity

    # ------------------------------------------------------------------
    # Password-specific helpers
    # ------------------------------------------------------------------

    async def verify_password_credentials(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
    ) -> User | None:
        """Return the matching user iff (email, password) verifies.

        Resolution order:

        1. ``user_identities`` row with ``provider='password'`` and
           ``subject=email`` (post-0018 source of truth).
        2. Legacy ``users.hashed_password`` fallback — for the brief
           window where the password user existed before 0018 ran AND
           service code rolled forward before the operator ran the
           backfill. The fallback **also** writes the verified password
           into ``user_identities`` so the next login skips the legacy
           path entirely.

        Returns ``None`` for "no such email" AND "wrong password" so the
        caller cannot accidentally leak which one happened (avoids
        account enumeration).
        """
        identity = await self.find(session, provider=PROVIDER_PASSWORD, subject=email)

        if identity is not None and identity.credential is not None:
            if not verify_password(password, identity.credential):
                return None
            return await session.get(User, identity.user_id)

        # ---- legacy fallback ----
        user = await session.scalar(select(User).where(User.email == email))
        if user is None or user.hashed_password is None:
            return None
        if not verify_password(password, user.hashed_password):
            return None

        # Lazy backfill: the next login won't hit this branch.
        if identity is None:
            self.attach(
                session,
                user_id=user.id,
                provider=PROVIDER_PASSWORD,
                subject=email,
                credential=user.hashed_password,
            )

        return user

    def create_password_identity(
        self,
        session: AsyncSession,
        *,
        user_id: uuid.UUID,
        email: str,
        password: str,
    ) -> UserIdentity:
        """Sugar for ``attach(provider='password', credential=hash(password))``."""
        return self.attach(
            session,
            user_id=user_id,
            provider=PROVIDER_PASSWORD,
            subject=email,
            credential=hash_password(password),
        )
