"""``user_identities`` — pluggable login methods per user.

Background
----------
Up to migration 0017 a user authenticated via exactly one mechanism: the
``users.hashed_password`` column. P-AUTH-2 (this module) decouples
"who you are" (``users``) from "how you proved it" (``user_identities``)
so the same account can later attach email-OTP, GitHub OAuth, WeChat,
etc. without touching the core ``users`` table again.

Schema shape
~~~~~~~~~~~~
* ``provider`` — short label, e.g. ``password``, ``email_otp``, ``github``.
* ``subject``  — the identifier under that provider:
                 ``password`` & ``email_otp`` → the email,
                 ``github``                   → the numeric GitHub user id,
                 ``wechat``                   → ``unionid`` (NOT ``openid``).
* ``credential`` — provider-specific verifier; for ``password`` this is
                  the bcrypt hash. ``NULL`` for OAuth providers.
* ``metadata``   — JSONB bag for provider-specific profile bits we want
                  cached (avatar URL, screen name, etc). Optional.

Uniqueness ``(provider, subject)`` is enforced so the same external
identity cannot map to two local users.

Migration policy
~~~~~~~~~~~~~~~~
The accompanying alembic 0018 backfills one row per existing
``users`` record (provider=``password``, subject=email,
credential=hashed_password). After backfill, ``users.hashed_password``
becomes nullable but is *not* dropped — it stays as a read-only fallback
for one release cycle so we can rollback the service code without
losing data. New writes must go through ``UserIdentity``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from service.db.base import Base
from service.db.models._mixins import TimestampMixin, UUIDMixin

__all__ = ["UserIdentity"]


# Same hybrid type the rest of the codebase uses (Postgres JSONB / SQLite JSON).
_JSON_TYPE = JSON().with_variant(postgresql.JSONB(), "postgresql")


class UserIdentity(UUIDMixin, TimestampMixin, Base):
    """One row = one (user, provider) pairing."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_user_identities_provider_subject"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    # ``credential`` doubles as the bcrypt hash for password / email-OTP-derived
    # accounts. OAuth providers leave it NULL because the IdP holds the secret.
    credential: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Provider-specific cached profile. We keep this small (avatar, login,
    # display name); never store IdP access tokens here — those belong in
    # a separate, encrypted table when we need them.
    identity_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        _JSON_TYPE,
        nullable=True,
    )
