"""ChatService orchestration behaviour."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.chat_service import ChatService
from core.knowledge.base import KnowledgeHit
from core.memory.chat_memory import FileChatMemory


class _StaticKB:
    """Minimal KB returning a fixed hit list, for retrieval-path tests."""

    def __init__(self, hits: list[KnowledgeHit]) -> None:
        self._hits = hits

    async def search(self, query: str, *, top_k: int = 4) -> list[KnowledgeHit]:
        del query, top_k
        return list(self._hits)


async def _drain(gen: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    async for ev in gen:
        events.append(ev)
    return events


@pytest.mark.asyncio
async def test_happy_path_emits_tokens_then_done(tmp_path: Path, fake_llm_factory: type) -> None:
    llm = fake_llm_factory(deltas=["hel", "lo"])
    memory = FileChatMemory(root=tmp_path)
    service = ChatService(llm=llm, memory=memory)
    sid = await service.new_session()

    events = await _drain(service.generate(sid, "hi"))
    types = [e["type"] for e in events]

    assert types == ["token", "token", "done"]
    assert "".join(e["delta"] for e in events if e["type"] == "token") == "hello"
    assert events[-1]["usage"] == {"eval_count": 42}

    stored = await memory.get(sid)
    assert [(m.role, m.content) for m in stored] == [
        ("user", "hi"),
        ("assistant", "hello"),
    ]


@pytest.mark.asyncio
async def test_retrieval_event_before_tokens_when_enabled(
    tmp_path: Path, fake_llm_factory: type
) -> None:
    llm = fake_llm_factory(deltas=["ok"])
    memory = FileChatMemory(root=tmp_path)
    kb = _StaticKB([KnowledgeHit(title="t", content="c", score=0.9, source="unit")])
    service = ChatService(llm=llm, memory=memory, knowledge=kb)
    sid = await service.new_session()

    events = await _drain(service.generate(sid, "ask", use_rag=True))
    types = [e["type"] for e in events]

    assert types[0] == "retrieval"
    assert events[0]["hits"][0]["title"] == "t"
    assert "token" in types and types[-1] == "done"


@pytest.mark.asyncio
async def test_llm_error_is_reported_not_raised(tmp_path: Path) -> None:
    from core.llm.client import LLMError

    class _Boom:
        async def chat_stream(self, *a: Any, **k: Any) -> Any:
            raise LLMError("boom")
            yield  # make it a generator

        async def embed(self, *a: Any, **k: Any) -> Any:  # pragma: no cover
            raise LLMError("boom")

        async def aclose(self) -> None:
            return None

    service = ChatService(llm=_Boom(), memory=FileChatMemory(root=tmp_path))
    sid = await service.new_session()

    events = await _drain(service.generate(sid, "hi"))
    assert events == [{"type": "error", "code": "llm_error", "message": "boom"}]
    # Memory should stay clean on failure.
    assert await FileChatMemory(root=tmp_path).get(sid) == []
