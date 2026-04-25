"""ChatService abort + generate_full coverage."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from core.chat_service import ChatService
from core.llm.client import ChatChunk, ChatMessage
from core.memory.chat_memory import FileChatMemory


class _SlowLLM:
    """Yields one token at a time and awaits an abort check between deltas.

    Mirrors the real Ollama stream for abort-timing purposes.
    """

    def __init__(self, deltas: list[str]) -> None:
        self.deltas = deltas
        self.yielded = 0

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
    ) -> AsyncIterator[ChatChunk]:
        del messages, model
        for delta in self.deltas:
            yield ChatChunk(delta=delta, done=False)
            self.yielded += 1
        yield ChatChunk(delta="", done=True, usage={"eval_count": self.yielded})

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        del model
        return [[0.0] for _ in texts]

    async def aclose(self) -> None:
        pass


@pytest.fixture
def memory(tmp_path: Path) -> FileChatMemory:
    return FileChatMemory(root=tmp_path)


async def test_abort_mid_stream_emits_aborted_event(memory: FileChatMemory) -> None:
    from core.streaming.abort import AbortContext

    llm = _SlowLLM(["a", "b", "c", "d", "e"])
    svc = ChatService(llm=llm, memory=memory)
    abort = AbortContext()

    sid = await memory.new_session()
    events: list[dict[str, object]] = []
    async for evt in svc.generate(sid, "hi", abort=abort):
        events.append(evt)
        # Abort right after the second token.
        if evt.get("type") == "token" and len([e for e in events if e.get("type") == "token"]) == 2:
            abort.abort()

    # Last event must be the ABORTED error.
    assert events[-1] == {
        "type": "error",
        "code": "ABORTED",
        "message": "client aborted the stream",
    }
    # And we did not yield a terminal `done`.
    assert not any(e.get("type") == "done" for e in events)


async def test_abort_before_start_short_circuits(memory: FileChatMemory) -> None:
    from core.streaming.abort import AbortContext

    llm = _SlowLLM(["a", "b"])
    svc = ChatService(llm=llm, memory=memory)
    abort = AbortContext()
    abort.abort()

    sid = await memory.new_session()
    events = [evt async for evt in svc.generate(sid, "hi", abort=abort)]
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["code"] == "ABORTED"
    # LLM was never consulted.
    assert llm.yielded == 0


async def test_generate_full_happy_path(memory: FileChatMemory) -> None:
    llm = _SlowLLM(["hello ", "world"])
    svc = ChatService(llm=llm, memory=memory)

    sid = await memory.new_session()
    result = await svc.generate_full(sid, "hi")
    assert result["content"] == "hello world"
    assert result["error"] is None
    assert result["usage"] == {"eval_count": 2}
    assert isinstance(result["duration_ms"], int)


async def test_generate_full_surfaces_error(memory: FileChatMemory) -> None:
    class _Boom:
        async def chat_stream(
            self, messages: list[ChatMessage], *, model: str | None = None
        ) -> AsyncIterator[ChatChunk]:
            # Make this a real async generator; raise on first pull.
            if False:
                yield  # pragma: no cover
            raise RuntimeError("upstream dead")

        async def embed(self, texts: list[str], *, model: str | None = None) -> list[list[float]]:
            return [[0.0] for _ in texts]

        async def aclose(self) -> None:
            pass

    svc = ChatService(llm=_Boom(), memory=memory)
    sid = await memory.new_session()
    result = await svc.generate_full(sid, "hi")
    assert result["content"] == ""
    assert result["error"] is not None
    assert result["error"]["code"] == "unexpected"
