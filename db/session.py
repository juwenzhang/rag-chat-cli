"""Async engine + session plumbing.

Design rules (AGENTS.md §4 / §15 P4):

* **Module-level singletons** (``_engine`` / ``_SessionLocal``) are created
  on the first :func:`init_engine` call and reused thereafter.
* **No implicit init**: importing this module does *not* open any
  connection. The CLI still boots when Postgres is unreachable.
* **Async only**: this is a SQLAlchemy 2.x asyncio surface; there is no
  sync equivalent. FastAPI handlers (added by P6) depend on
  :func:`get_session`.

Typical usage::

    from db.session import init_engine, get_session, dispose_engine

    await init_engine()                     # uses settings.db.database_url
    async for session in get_session():     # FastAPI-style dependency
        ...
    await dispose_engine()

For SQLite in-memory testing::

    await init_engine("sqlite+aiosqlite:///:memory:")
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

__all__ = [
    "current_engine",
    "dispose_engine",
    "get_session",
    "init_engine",
]


_engine: AsyncEngine | None = None
_SessionLocal: async_sessionmaker[AsyncSession] | None = None


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def init_engine(url: str | None = None, *, echo: bool | None = None) -> AsyncEngine:
    """Create (or reuse) the module-level async engine.

    Args:
        url: Database URL. Defaults to ``settings.db.database_url``.
        echo: If given, overrides ``settings.db.echo_sql``. Useful in tests.

    Returns:
        The live :class:`AsyncEngine`.
    """

    global _engine, _SessionLocal

    # Late-import settings so that importing `db.session` does NOT force the
    # settings singleton to load; that keeps the CLI boot path DB-agnostic.
    from settings import settings

    resolved_url = url or settings.db.database_url
    resolved_echo = settings.db.echo_sql if echo is None else echo

    if _engine is not None:
        return _engine

    if _is_sqlite(resolved_url):
        # SQLite does not support pool_size / pool_recycle; skip them to avoid
        # warnings. `aiosqlite` provides its own single-writer semantics.
        _engine = create_async_engine(resolved_url, echo=resolved_echo, future=True)
    else:
        _engine = create_async_engine(
            resolved_url,
            echo=resolved_echo,
            future=True,
            pool_size=settings.db.pool_size,
            pool_recycle=settings.db.pool_recycle,
            pool_pre_ping=True,
        )

    _SessionLocal = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def current_engine() -> AsyncEngine:
    """Return the initialised engine or raise if :func:`init_engine` was not called."""

    if _engine is None:
        raise RuntimeError("db.session.init_engine() has not been called yet")
    return _engine


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-style dependency yielding a single :class:`AsyncSession`.

    The session commits nothing implicitly — callers are responsible for
    ``session.commit()`` / ``rollback()``. On scope exit the session is
    always closed.
    """

    if _SessionLocal is None:
        raise RuntimeError("db.session.init_engine() has not been called yet")

    async with _SessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    """Close the engine; safe to call multiple times."""

    global _engine, _SessionLocal
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _SessionLocal = None
