"""add providers + user_preferences, link chat_sessions to provider/model

Revision ID: 0004_providers_prefs
Revises: 0003_add_user_memories
Create Date: 2026-05-12

Per-user LLM provider registry (Ollama, OpenAI-compatible, …). Each row is
one configured endpoint; users may register many and pick one as default.
``user_preferences`` holds the per-user default provider/model/RAG toggle.
``chat_sessions`` gains optional ``provider_id`` + ``model`` so an individual
conversation can pin a different provider/model than the user default.

API keys are stored encrypted (Fernet) — see ``core.providers``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_providers_prefs"
down_revision: str | None = "0003_add_user_memories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    # ------------------------------------------------------------------
    # providers
    # ------------------------------------------------------------------
    op.create_table(
        "providers",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        # "ollama" | "openai" (OpenAI-compatible, incl. OpenRouter / Together / DeepSeek).
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        # Fernet-encrypted; NULL for keyless backends (local Ollama on default port).
        sa.Column("api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_providers_user_id_users",
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_providers_user_id_name"),
    )
    op.create_index("ix_providers_user_id", "providers", ["user_id"])

    # ------------------------------------------------------------------
    # user_preferences (1 row per user)
    # ------------------------------------------------------------------
    op.create_table(
        "user_preferences",
        sa.Column("user_id", _UUID, primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("default_provider_id", _UUID, nullable=True),
        sa.Column("default_model", sa.String(128), nullable=True),
        sa.Column(
            "default_use_rag",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_user_preferences_user_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["default_provider_id"],
            ["providers.id"],
            ondelete="SET NULL",
            name="fk_user_preferences_default_provider_id_providers",
        ),
    )

    # ------------------------------------------------------------------
    # chat_sessions: optional pin
    # ------------------------------------------------------------------
    with op.batch_alter_table("chat_sessions") as batch:
        batch.add_column(sa.Column("provider_id", _UUID, nullable=True))
        batch.add_column(sa.Column("model", sa.String(128), nullable=True))
        batch.create_foreign_key(
            "fk_chat_sessions_provider_id_providers",
            "providers",
            ["provider_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch:
        batch.drop_constraint(
            "fk_chat_sessions_provider_id_providers", type_="foreignkey"
        )
        batch.drop_column("model")
        batch.drop_column("provider_id")

    op.drop_table("user_preferences")
    op.drop_index("ix_providers_user_id", table_name="providers")
    op.drop_table("providers")
