"""Smoke tests for the six ORM models on SQLite + the Vector JSON fallback."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ChatSession, Chunk, Document, Message, RefreshToken, User


@pytest.mark.asyncio
async def test_user_chatsession_message_roundtrip(
    async_session: AsyncSession,
) -> None:
    user = User(
        email="alice@example.com",
        hashed_password="bcrypt$placeholder",
        display_name="Alice",
    )
    async_session.add(user)
    await async_session.flush()

    chat = ChatSession(user_id=user.id, title="Trip planning")
    async_session.add(chat)
    await async_session.flush()

    msg = Message(session_id=chat.id, role="user", content="Hi")
    async_session.add(msg)
    await async_session.commit()

    row = (
        await async_session.execute(select(Message).where(Message.session_id == chat.id))
    ).scalar_one()
    assert row.content == "Hi"
    assert row.role == "user"


@pytest.mark.asyncio
async def test_document_meta_json_roundtrip(async_session: AsyncSession) -> None:
    doc = Document(
        source="https://example.com/a.pdf",
        title="Paper A",
        meta={"lang": "en", "tags": ["rag", "llm"]},
    )
    async_session.add(doc)
    await async_session.commit()

    loaded = (
        await async_session.execute(select(Document).where(Document.id == doc.id))
    ).scalar_one()
    assert loaded.meta["lang"] == "en"
    assert loaded.meta["tags"] == ["rag", "llm"]


@pytest.mark.asyncio
async def test_chunk_embedding_roundtrip_on_sqlite(
    async_session: AsyncSession,
) -> None:
    """On SQLite the Vector column falls back to JSON; values should
    survive a round-trip as floats."""

    doc = Document(source="inline", title="inline")
    async_session.add(doc)
    await async_session.flush()

    vec = [0.1, 0.2, 0.3] + [0.0] * 765  # 768-dim
    chunk = Chunk(document_id=doc.id, seq=0, content="hello world", embedding=vec)
    async_session.add(chunk)
    await async_session.commit()

    loaded = (await async_session.execute(select(Chunk).where(Chunk.id == chunk.id))).scalar_one()
    assert loaded.content == "hello world"
    assert isinstance(loaded.embedding, list)
    assert len(loaded.embedding) == 768
    assert pytest.approx(loaded.embedding[0]) == 0.1
    assert pytest.approx(loaded.embedding[2]) == 0.3


@pytest.mark.asyncio
async def test_refresh_token_row(async_session: AsyncSession) -> None:
    user = User(email="b@example.com", hashed_password="x")
    async_session.add(user)
    await async_session.flush()

    token = RefreshToken(
        user_id=user.id,
        jti="abc-123",
        expires_at=datetime.now(tz=timezone.utc) + timedelta(days=7),
    )
    async_session.add(token)
    await async_session.commit()

    loaded = (
        await async_session.execute(select(RefreshToken).where(RefreshToken.jti == "abc-123"))
    ).scalar_one()
    assert loaded.user_id == user.id
    assert loaded.revoked_at is None
