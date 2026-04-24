"""High-level chat orchestration.

:class:`ChatService` is the single seam between :mod:`app` and the rest of
:mod:`core`. It owns an :class:`~core.llm.client.LLMClient`, a
:class:`~core.memory.chat_memory.ChatMemory` and an optional
:class:`~core.knowledge.base.KnowledgeBase`, and exposes a single async
generator :meth:`generate` that yields events already aligned with
``AGENTS.md §5.3`` (``retrieval / token / done / error``).

The event dict shape matches :class:`ui.chat_view.Event` so the UI layer
can consume the stream verbatim.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any

from core.knowledge.base import KnowledgeBase
from core.llm.client import ChatMessage, LLMClient, LLMError
from core.memory.chat_memory import ChatMemory

__all__ = ["ChatService"]

Event = dict[str, Any]


class ChatService:
    """Glue between LLM, memory and (optionally) a retriever."""

    def __init__(
        self,
        llm: LLMClient,
        memory: ChatMemory,
        knowledge: KnowledgeBase | None = None,
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._kb = knowledge

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def aclose(self) -> None:
        """Close the underlying LLM client."""
        await self._llm.aclose()

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------
    async def new_session(self) -> str:
        return await self._memory.new_session()

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------
    async def generate(
        self,
        session_id: str,
        user_text: str,
        *,
        use_rag: bool = False,
        top_k: int = 4,
    ) -> AsyncIterator[Event]:
        """Stream the full reply loop as UI-facing events.

        Order of emitted events:
          1. optional ``retrieval`` (when ``use_rag`` and a KB is configured)
          2. zero or more ``token`` events
          3. exactly one of ``done`` or ``error``

        Side-effects: on a successful run the ``user`` and ``assistant``
        messages are appended to the in-memory store.
        """

        started = time.monotonic()

        # 0. Load history from memory (best-effort — new sessions yield []).
        try:
            history = await self._memory.get(session_id)
        except Exception as exc:
            yield {
                "type": "error",
                "code": "memory_read_failed",
                "message": str(exc),
            }
            return

        # 1. Optional retrieval.
        if use_rag and self._kb is not None:
            try:
                hits = await self._kb.search(user_text, top_k=top_k)
            except Exception as exc:
                yield {
                    "type": "error",
                    "code": "retrieval_failed",
                    "message": str(exc),
                }
                return
            yield {
                "type": "retrieval",
                "hits": [
                    {
                        "title": h.title,
                        "content": h.content,
                        "score": h.score,
                        "source": h.source,
                    }
                    for h in hits
                ],
            }

        # 2. Build messages + stream tokens.
        messages: list[ChatMessage] = [
            *history,
            ChatMessage(role="user", content=user_text),
        ]
        collected: list[str] = []
        usage: dict[str, Any] | None = None
        try:
            async for chunk in self._llm.chat_stream(messages):
                if chunk.delta:
                    collected.append(chunk.delta)
                    yield {"type": "token", "delta": chunk.delta}
                if chunk.done:
                    usage = dict(chunk.usage) if chunk.usage else None
        except LLMError as exc:
            yield {
                "type": "error",
                "code": "llm_error",
                "message": str(exc),
            }
            return
        except Exception as exc:
            yield {
                "type": "error",
                "code": "unexpected",
                "message": f"{type(exc).__name__}: {exc}",
            }
            return

        # 3. Persist both sides of the exchange.
        assistant_text = "".join(collected)
        try:
            await self._memory.append(session_id, ChatMessage(role="user", content=user_text))
            await self._memory.append(
                session_id,
                ChatMessage(role="assistant", content=assistant_text),
            )
        except Exception as exc:
            yield {
                "type": "error",
                "code": "memory_write_failed",
                "message": str(exc),
            }
            return

        # 4. Terminator.
        duration_ms = int((time.monotonic() - started) * 1000)
        done: Event = {"type": "done", "duration_ms": duration_ms}
        if usage is not None:
            done["usage"] = usage
        yield done
