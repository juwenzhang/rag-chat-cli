"""Alembic async env — AGENTS.md §4 / P4 change design.

Key decisions:

* URL is read from ``settings.db.database_url`` at runtime; it is *not*
  stored in ``alembic.ini``.
* ``import db.models`` triggers ORM registration before
  ``target_metadata`` is read.
* ``render_as_batch=True`` on SQLite so the ``alembic upgrade`` path
  also works under the test harness (SQLite cannot ALTER TABLE natively).
* ``compare_type=True`` so autogenerate catches ``VARCHAR(100)`` →
  ``VARCHAR(255)`` style changes.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config

from alembic import context

# ---------------------------------------------------------------------------
# Boilerplate wiring
# ---------------------------------------------------------------------------

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import settings lazily so failures surface with a clear message.
# Register all ORM models so Base.metadata is populated.
import db.models  # noqa: E402, F401  — side-effect import
from db.base import Base  # noqa: E402
from settings import settings  # noqa: E402

target_metadata = Base.metadata


def _db_url() -> str:
    """URL precedence: Alembic CLI ``-x url=...`` → settings."""
    x_args = context.get_x_argument(as_dictionary=True)
    return x_args.get("url") or settings.db.database_url


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


# ---------------------------------------------------------------------------
# Offline (emit SQL to stdout — no DB connection)
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    url = _db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=_is_sqlite(url),
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online (real connection; async-aware)
# ---------------------------------------------------------------------------


def _do_run_migrations(connection: Connection) -> None:
    url = _db_url()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=_is_sqlite(url),
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async_migrations() -> None:
    url = _db_url()
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url

    connectable: AsyncEngine = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


def _run_sync_migrations() -> None:
    """SQLite (or other sync drivers) path — no asyncio needed."""
    url = _db_url()
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = url

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )
    with connectable.connect() as connection:
        _do_run_migrations(connection)
    connectable.dispose()


def run_migrations_online() -> None:
    url = _db_url()
    # ``sqlite+aiosqlite`` is still async; ``sqlite://`` is sync.
    if url.startswith("sqlite+") or url.startswith(
        ("postgresql+asyncpg", "postgresql+psycopg_async")
    ):
        asyncio.run(_run_async_migrations())
    else:
        _run_sync_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
