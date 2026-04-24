"""Tests for :mod:`db.session` basic plumbing."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import db.session as db_session


@pytest.fixture(autouse=True)
def _reset_module_state() -> None:
    """Ensure each test starts with no cached engine."""
    db_session._engine = None
    db_session._SessionLocal = None


@pytest.mark.asyncio
async def test_init_engine_creates_and_reuses() -> None:
    engine = db_session.init_engine("sqlite+aiosqlite:///:memory:")
    assert isinstance(engine, AsyncEngine)
    assert db_session.current_engine() is engine

    # A second call should return the same engine instance (cached).
    assert db_session.init_engine("sqlite+aiosqlite:///:memory:") is engine

    await db_session.dispose_engine()


@pytest.mark.asyncio
async def test_current_engine_raises_before_init() -> None:
    with pytest.raises(RuntimeError, match="init_engine"):
        db_session.current_engine()


@pytest.mark.asyncio
async def test_get_session_yields_working_session() -> None:
    db_session.init_engine("sqlite+aiosqlite:///:memory:")

    # get_session() is an async-generator function; convert to AsyncGenerator
    # for a well-typed aclose().
    from collections.abc import AsyncGenerator
    from typing import cast

    agen = cast(AsyncGenerator["AsyncSession", None], db_session.get_session())
    try:
        session = await agen.__anext__()
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
    finally:
        await agen.aclose()
        await db_session.dispose_engine()


@pytest.mark.asyncio
async def test_dispose_is_idempotent() -> None:
    db_session.init_engine("sqlite+aiosqlite:///:memory:")
    await db_session.dispose_engine()
    await db_session.dispose_engine()  # no exception
