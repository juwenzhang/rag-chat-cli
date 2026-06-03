"""add asset upload hashes

Revision ID: 0016_asset_hashes
Revises: 0015_assets
Create Date: 2026-06-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_asset_hashes"
down_revision: str | None = "0015_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("source_hash", sa.String(64), nullable=True))
    op.add_column("assets", sa.Column("content_hash", sa.String(64), nullable=True))
    op.create_index(
        "ix_assets_user_id_source_hash",
        "assets",
        ["user_id", "source_hash"],
        unique=True,
    )
    op.create_index(
        "ix_assets_user_id_content_hash",
        "assets",
        ["user_id", "content_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_assets_user_id_content_hash", table_name="assets")
    op.drop_index("ix_assets_user_id_source_hash", table_name="assets")
    op.drop_column("assets", "content_hash")
    op.drop_column("assets", "source_hash")
