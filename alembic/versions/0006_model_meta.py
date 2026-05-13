"""add model_metadata (per-(provider, model) free-text description)

Revision ID: 0006_model_meta
Revises: 0005_embed_pref
Create Date: 2026-05-13

Lets users attach a free-text description to any model they add — shown
as a hover tooltip in the chat model picker and the providers settings
page. Provider ownership transitively scopes to a user, so the row keys
on ``(provider_id, model)`` and cascades on provider delete.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_model_meta"
down_revision: str | None = "0005_embed_pref"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.create_table(
        "model_metadata",
        sa.Column("provider_id", _UUID, primary_key=True),
        sa.Column("model", sa.String(256), primary_key=True),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["providers.id"],
            ondelete="CASCADE",
            name="fk_model_metadata_provider_id_providers",
        ),
    )


def downgrade() -> None:
    op.drop_table("model_metadata")
