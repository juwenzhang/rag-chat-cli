"""File-backed ChatMemory behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.llm.client import ChatMessage
from core.memory.chat_memory import FileChatMemory


@pytest.mark.asyncio
async def test_new_session_is_isolated(tmp_path: Path) -> None:
    mem = FileChatMemory(root=tmp_path)
    sid_a = await mem.new_session()
    sid_b = await mem.new_session()
    assert sid_a != sid_b
    assert sorted(await mem.list_sessions()) == sorted([sid_a, sid_b])


@pytest.mark.asyncio
async def test_append_and_get_roundtrip(tmp_path: Path) -> None:
    mem = FileChatMemory(root=tmp_path)
    sid = await mem.new_session()
    await mem.append(sid, ChatMessage(role="user", content="hi"))
    await mem.append(sid, ChatMessage(role="assistant", content="hello"))
    msgs = await mem.get(sid)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[1].content == "hello"


@pytest.mark.asyncio
async def test_delete_session(tmp_path: Path) -> None:
    mem = FileChatMemory(root=tmp_path)
    sid = await mem.new_session()
    await mem.delete_session(sid)
    assert await mem.list_sessions() == []


@pytest.mark.asyncio
async def test_rejects_unsafe_session_id(tmp_path: Path) -> None:
    mem = FileChatMemory(root=tmp_path)
    with pytest.raises(ValueError):
        await mem.get("../etc/passwd")
