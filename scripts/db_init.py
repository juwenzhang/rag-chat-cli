#!/usr/bin/env python
"""One-shot database bootstrap: probe connectivity, upgrade to head, assert
pgvector is installed.

Usage::

    # after `docker compose --profile db up -d postgres`
    uv run python scripts/db_init.py

The script prefers ``DB__DATABASE_URL`` from the environment (via
``settings``) but accepts an override argv::

    python scripts/db_init.py postgresql+asyncpg://rag:rag@localhost:5432/ragdb
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure repo root is on sys.path when the script is invoked directly.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from alembic import command  # noqa: E402


async def _probe(url: str) -> None:
    """Raise if the DB is unreachable."""
    engine = create_async_engine(url, future=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def _check_pgvector(url: str) -> bool:
    engine = create_async_engine(url, future=True)
    try:
        async with engine.connect() as conn:
            row = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            return row.first() is not None
    finally:
        await engine.dispose()


def _run_migrations(url: str) -> None:
    cfg = Config(str(_ROOT / "alembic.ini"))
    # Pass URL via -x so env.py picks it up without persisting to ini.
    cfg.cmd_opts = None  # reset any cached state
    cfg.attributes["x"] = {"url": url}
    # Alembic reads x-args from context.get_x_argument() — we need to put
    # the URL where env.py can find it. Easiest: set it via the CLI
    # surrogate by exporting DATABASE_URL temporarily.
    import os

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        command.upgrade(cfg, "head")
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql")


async def _main() -> int:
    # Resolve URL: argv[1] > settings.db.database_url.
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        from settings import settings

        url = settings.db.database_url

    print(f"[db-init] target: {url}")

    try:
        await _probe(url)
    except Exception as exc:
        print(f"[db-init] ERROR: cannot reach DB: {exc}")
        return 1
    print("[db-init] connectivity: OK")

    # Run alembic in a dedicated thread so its internal asyncio.run() does
    # not clash with the event loop we are already running inside.
    await asyncio.to_thread(_run_migrations, url)
    print("[db-init] migrations: at head")

    if _is_postgres(url):
        ok = await _check_pgvector(url)
        if not ok:
            print("[db-init] ERROR: pgvector extension not found")
            return 2
        print("[db-init] pgvector: installed")
    else:
        print("[db-init] pgvector: skipped (non-postgres dialect)")

    print("[db-init] done")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
