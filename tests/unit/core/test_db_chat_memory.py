"""DbChatMemory behaviour — roundtrip + cross-user isolation.

Uses the ``async_engine`` fixture (in-memory SQLite) to avoid any real DB
dependency. Two tests only, per the "keep tests lightweight" directive.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from core.llm.client import ChatMessage
from core.memory.chat_memory import DbChatMemory
from db.models import User


async def _seed_user(sf: async_sessionmaker[AsyncSession], *, email: str) -> uuid.UUID:
    async with sf() as s:
        row = User(email=email, hashed_password="x", display_name=None, is_active=True)
        s.add(row)
        await s.commit()
        return row.id


@pytest.mark.asyncio
async def test_roundtrip_new_append_get_delete(async_engine: object) -> None:
    assert isinstance(async_engine, AsyncEngine)
    sf = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)
    user_id = await _seed_user(sf, email="a@example.com")

    mem = DbChatMemory(session_factory=sf, user_id=user_id)
    sid = await mem.new_session()
    assert uuid.UUID(sid)  # sid is a valid UUID string

    await mem.append(sid, ChatMessage(role="user", content="hi"))
    await mem.append(sid, ChatMessage(role="assistant", content="hello"))

    msgs = await mem.get(sid)
    assert [(m.role, m.content) for m in msgs] == [("user", "hi"), ("assistant", "hello")]

    assert sid in await mem.list_sessions()

    await mem.delete_session(sid)
    assert await mem.get(sid) == []  # FK cascade wiped messages
    assert await mem.list_sessions() == []


@pytest.mark.asyncio
async def test_cross_user_isolation(async_engine: object) -> None:
    assert isinstance(async_engine, AsyncEngine)
    sf = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

    user_a = await _seed_user(sf, email="a@example.com")
    user_b = await _seed_user(sf, email="b@example.com")

    mem_a = DbChatMemory(session_factory=sf, user_id=user_a)
    mem_b = DbChatMemory(session_factory=sf, user_id=user_b)

    sid = await mem_a.new_session()
    await mem_a.append(sid, ChatMessage(role="user", content="secret"))

    # User B must not see User A's session or messages.
    assert await mem_b.get(sid) == []
    assert sid not in await mem_b.list_sessions()

    # And delete_session from B is a no-op on A's session (not an exception).
    await mem_b.delete_session(sid)
    assert [(m.role, m.content) for m in await mem_a.get(sid)] == [("user", "secret")]
