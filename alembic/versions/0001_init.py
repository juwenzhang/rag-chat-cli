"""init — users / chat_sessions / messages / documents / chunks / refresh_tokens

Revision ID: 0001_init
Revises:
Create Date: 2026-04-24

Notes:
* Runs on **Postgres + pgvector** in production: creates the ``vector``
  and ``pg_trgm`` extensions, the ``chunks.embedding vector(dim)`` column,
  and the ``ix_chunks_embedding_ivfflat`` index.
* Runs on **SQLite** in tests: extension statements are no-ops,
  ``embedding`` degrades to JSON text (see ``db/models/chunk.py``),
  and the ivfflat index statement is skipped.
* Dimension is read from ``settings.retrieval.embed_dim`` so bumping
  the embedding model needs one place of change + a fresh migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Vector column helper — Postgres uses pgvector.Vector(dim); everything
# else gets the JSON TypeDecorator defined on the ORM side (we just use
# sa.JSON here because Alembic only needs a shape, not fidelity).
def _embed_dim() -> int:
    try:
        from settings import settings

        return int(settings.retrieval.embed_dim)
    except Exception:
        return 768


def _vector_type() -> sa.types.TypeEngine[object]:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from pgvector.sqlalchemy import Vector

        # pgvector.sqlalchemy lacks py.typed; the return is Any -> cast.
        return Vector(_embed_dim())  # type: ignore[no-any-return]
    return sa.JSON()


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


# PG UUID that degrades to String(36) elsewhere.
_UUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # users -----------------------------------------------------------------
    op.create_table(
        "users",
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
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # chat_sessions ---------------------------------------------------------
    op.create_table(
        "chat_sessions",
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
        sa.Column("title", sa.String(256), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_chat_sessions_user_id_users",
        ),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])

    # messages --------------------------------------------------------------
    op.create_table(
        "messages",
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
        sa.Column("session_id", _UUID, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tokens", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            ondelete="CASCADE",
            name="fk_messages_session_id_chat_sessions",
        ),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])

    # documents -------------------------------------------------------------
    meta_type: sa.types.TypeEngine[object]
    if _is_postgres():
        meta_type = postgresql.JSONB()
    else:
        meta_type = sa.JSON()

    op.create_table(
        "documents",
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
        sa.Column("user_id", _UUID, nullable=True),
        sa.Column("source", sa.String(512), nullable=False),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("meta", meta_type, nullable=False, server_default=sa.text("'{}'")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_documents_user_id_users",
        ),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])

    # chunks ----------------------------------------------------------------
    op.create_table(
        "chunks",
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
        sa.Column("document_id", _UUID, nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", _vector_type(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
            name="fk_chunks_document_id_documents",
        ),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])

    # ivfflat is Postgres/pgvector-only; skip elsewhere (test harness).
    if _is_postgres():
        op.execute(
            "CREATE INDEX ix_chunks_embedding_ivfflat "
            "ON chunks USING ivfflat (embedding vector_cosine_ops) "
            "WITH (lists = 100)"
        )

    # refresh_tokens --------------------------------------------------------
    op.create_table(
        "refresh_tokens",
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
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_refresh_tokens_user_id_users",
        ),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_jti", "refresh_tokens", ["jti"], unique=True)


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    # Extensions are intentionally kept: they are schema-wide and
    # re-creating them is idempotent. Drop is order-sensitive (FKs).
    op.drop_index("ix_refresh_tokens_jti", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    if _is_postgres():
        op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_ivfflat")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")

    op.drop_index("ix_documents_user_id", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
