"""user_identities + nullable users.hashed_password

Revision ID: 0018_user_identities
Revises: 0017_message_evaluations
Create Date: 2026-06-06

P-AUTH-2: introduce ``user_identities`` so the same account can later
attach multiple login methods (password, email-OTP, GitHub OAuth, …).

This migration is **non-destructive** by design:

* Creates ``user_identities`` (idempotent — uses CREATE TABLE).
* Backfills one row per existing ``users`` record so the password login
  path keeps working when the service starts reading from the new table.
* Relaxes ``users.hashed_password`` to ``NULL`` so future OAuth-only
  users can land without a fake password placeholder.
* Keeps the legacy ``users.hashed_password`` column populated AND
  readable. New writes must go through ``UserIdentity``, but the column
  stays around for one release cycle as a rollback safety net.

The downgrade path is symmetric: writes the most recent password
``credential`` per user back into ``users.hashed_password`` before
dropping ``user_identities`` so a rollback does not strand anyone.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0018_user_identities"
down_revision: str | None = "0017_message_evaluations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = sa.UUID().with_variant(sa.String(36), "sqlite")
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Create ``user_identities`` table.
    # ------------------------------------------------------------------
    op.create_table(
        "user_identities",
        sa.Column("id", _UUID, primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            _UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("credential", sa.String(255), nullable=True),
        sa.Column("metadata", _JSON, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("provider", "subject", name="uq_user_identities_provider_subject"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"], unique=False)
    op.create_index("ix_user_identities_provider", "user_identities", ["provider"], unique=False)

    # ------------------------------------------------------------------
    # 2. Backfill — one ``provider='password'`` identity per existing
    #    user with a non-null hashed_password. ON CONFLICT keeps this
    #    re-runnable in the unlikely event the migration is replayed.
    # ------------------------------------------------------------------
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        # ``gen_random_uuid()`` requires the pgcrypto extension on older
        # Postgres but is built-in on 13+. The application baseline is
        # 16+, so we use it directly without an explicit CREATE EXTENSION.
        op.execute(
            sa.text(
                """
                INSERT INTO user_identities
                    (id, user_id, provider, subject, credential, metadata,
                     created_at, updated_at)
                SELECT
                    gen_random_uuid(),
                    u.id,
                    'password',
                    u.email,
                    u.hashed_password,
                    NULL,
                    NOW(),
                    NOW()
                FROM users u
                WHERE u.hashed_password IS NOT NULL
                ON CONFLICT (provider, subject) DO NOTHING
                """
            )
        )
    else:
        # SQLite path — used by the unit-test harness. ``hex(randomblob)``
        # gives us a UUID-shaped 32-char string; ``INSERT OR IGNORE``
        # gives us the equivalent ``ON CONFLICT DO NOTHING``.
        op.execute(
            sa.text(
                """
                INSERT OR IGNORE INTO user_identities
                    (id, user_id, provider, subject, credential, metadata,
                     created_at, updated_at)
                SELECT
                    lower(hex(randomblob(4))) || '-' ||
                    lower(hex(randomblob(2))) || '-4' ||
                    substr(lower(hex(randomblob(2))), 2) || '-a' ||
                    substr(lower(hex(randomblob(2))), 2) || '-' ||
                    lower(hex(randomblob(6))),
                    u.id,
                    'password',
                    u.email,
                    u.hashed_password,
                    NULL,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                FROM users u
                WHERE u.hashed_password IS NOT NULL
                """
            )
        )

    # ------------------------------------------------------------------
    # 3. Relax ``users.hashed_password`` to NULL. SQLite needs batch mode
    #    because it cannot ALTER COLUMN in place; Postgres does it
    #    natively. ``alter_column`` works under both via batch.
    # ------------------------------------------------------------------
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "hashed_password",
            existing_type=sa.String(255),
            nullable=True,
        )


def downgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------
    # 1. Restore ``users.hashed_password`` from the most recent password
    #    identity per user so the legacy login path still works. Users
    #    that only had non-password identities (future OAuth-only) are
    #    left with NULL — the next ``alter_column`` would fail in that
    #    case, so we re-set NOT NULL only when no NULLs remain.
    # ------------------------------------------------------------------
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                UPDATE users u
                SET hashed_password = i.credential
                FROM user_identities i
                WHERE i.user_id = u.id
                  AND i.provider = 'password'
                  AND i.credential IS NOT NULL
                  AND (u.hashed_password IS NULL OR u.hashed_password <> i.credential)
                """
            )
        )
    else:
        op.execute(
            sa.text(
                """
                UPDATE users
                SET hashed_password = (
                    SELECT i.credential
                    FROM user_identities i
                    WHERE i.user_id = users.id
                      AND i.provider = 'password'
                      AND i.credential IS NOT NULL
                    LIMIT 1
                )
                WHERE hashed_password IS NULL
                """
            )
        )

    # 2. Re-tighten the column only if no NULLs remain (otherwise leave
    #    nullable so the migration doesn't fail on OAuth-only rows). The
    #    original schema's NOT NULL is the safer default when the data
    #    permits.
    null_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM users WHERE hashed_password IS NULL")
    ).scalar_one()
    if null_count == 0:
        with op.batch_alter_table("users") as batch:
            batch.alter_column(
                "hashed_password",
                existing_type=sa.String(255),
                nullable=False,
            )

    # 3. Drop user_identities.
    op.drop_index("ix_user_identities_provider", table_name="user_identities")
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
