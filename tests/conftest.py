"""Top-level pytest fixtures — environment isolation + forthcoming test harness.

Kept deliberately small in P3. Heavier fixtures (``async_engine``, ``app_client``,
``redis_client``) land when the corresponding changes arrive:

* ``async_engine`` → **P4** ``setup-db-postgres-pgvector-alembic`` (this file)
* ``app_client``   → **P6** ``add-fastapi-rest-api``
* ``redis_client`` → **P5** ``add-redis-and-workers``

For now we need:

1. A session-scoped ``anyio_backend`` in case anyio-based code is added later.
2. An ``autouse`` fixture that clears environment-sensitive variables so that
   importing :mod:`settings` in a test subprocess never leaks the developer's
   real configuration.
3. A function-scoped :class:`sqlalchemy.ext.asyncio.AsyncEngine` fixture that
   builds an in-memory SQLite schema via ``Base.metadata.create_all`` so
   unit tests can exercise the ORM without a live Postgres.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio

_ENV_KEYS_TO_RESET = (
    "APP_ENV",
    "APP__ENV",
    "JWT_SECRET",
    "AUTH__JWT_SECRET",
    "DATABASE_URL",
    "DB__DATABASE_URL",
    "REDIS_URL",
    "REDIS__REDIS_URL",
    "OLLAMA_BASE_URL",
    "OLLAMA__BASE_URL",
)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Pin anyio to asyncio so async fixtures don't negotiate per-test."""
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Neutralise host env vars that would leak into Settings at import time."""
    for key in _ENV_KEYS_TO_RESET:
        monkeypatch.delenv(key, raising=False)
    # Always give auth a placeholder so ``Settings.load()`` never hard-fails.
    monkeypatch.setenv("APP__ENV", "dev")
    monkeypatch.setenv("AUTH__JWT_SECRET", "test-secret-not-for-prod-xxxxxxxxxxxxxxxx")
    yield


# NOTE: intentionally *not* importing ``settings`` here. Each test module that
# needs a fresh Settings instance imports it locally so the ``_reset_env``
# fixture has already taken effect before Settings reads os.environ.


# ---------------------------------------------------------------------------
# DB fixtures (P4)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_engine() -> AsyncIterator[object]:
    """In-memory SQLite async engine with the full ORM schema created.

    Returns the :class:`AsyncEngine` itself (typed as ``object`` to avoid an
    eager SQLAlchemy import in ``conftest``). Each test gets a fresh engine;
    tables are created via ``Base.metadata.create_all`` rather than Alembic
    for speed.
    """

    # Import lazily so tests that don't need DB don't pay the cost.
    from sqlalchemy.ext.asyncio import create_async_engine

    import db.models  # noqa: F401 — side-effect: register models
    from db.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine: object) -> AsyncIterator[object]:
    """One :class:`AsyncSession` per test, tied to :func:`async_engine`."""

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    assert isinstance(async_engine, AsyncEngine)
    maker = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
