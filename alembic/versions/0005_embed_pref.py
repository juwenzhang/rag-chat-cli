"""add user_preferences.default_embedding_model

Revision ID: 0005_embed_pref
Revises: 0004_providers_prefs
Create Date: 2026-05-13

Embedding models are picked from a disjoint set from chat models (nomic-
embed-text, bge-*, etc. can't chat; chat models can't embed). Storing a
separate default lets users pick per-domain (e.g. ``qwen2.5:1.5b`` for
chat + ``nomic-embed-text:latest`` for ingest).

NULL preserves the pre-migration behaviour: fall back to ``settings.ollama
.embedding_model`` (env / CLI defaults).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_embed_pref"
down_revision: str | None = "0004_providers_prefs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("default_embedding_model", sa.String(128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "default_embedding_model")
