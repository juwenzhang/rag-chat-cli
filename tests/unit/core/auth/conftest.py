"""Fixtures shared by core.auth service tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep bcrypt cheap. See ``test_password.py`` for rationale."""
    from core.auth import password as _pw

    _pw._context.cache_clear()
    from settings import settings

    monkeypatch.setattr(settings.auth, "bcrypt_rounds", 4, raising=True)


@pytest_asyncio.fixture
async def auth_service(async_engine: object) -> AsyncIterator[object]:
    """Build an :class:`AuthService` bound to the in-memory SQLite engine."""
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from core.auth.service import AuthService

    assert isinstance(async_engine, AsyncEngine)
    sf = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    yield AuthService(sf)
