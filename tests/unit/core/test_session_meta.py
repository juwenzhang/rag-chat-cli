"""SessionMeta synthesis on FileChatMemory — title preview from first user msg."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.llm.client import ChatMessage
from core.memory.chat_memory import FileChatMemory


@pytest.mark.asyncio
async def test_list_session_metas_synthesizes_title_from_first_user_msg(tmp_path: Path) -> None:
    mem = FileChatMemory(root=tmp_path)
    sid = await mem.new_session()
    long_text = "你好呀这是一段超过二十四字的中文用户消息用来测试截断功能能不能正确处理"
    await mem.append(sid, ChatMessage(role="user", content=long_text))
    await mem.append(sid, ChatMessage(role="assistant", content="收到"))

    metas = await mem.list_session_metas()
    assert len(metas) == 1
    meta = metas[0]
    assert meta.id == sid
    assert meta.message_count == 2
    # 24 chars + ellipsis ⇒ exactly 25 visible chars
    assert meta.title.endswith("…")
    # First 24 chars of the original must be a prefix.
    assert long_text.startswith(meta.title[:-1])
