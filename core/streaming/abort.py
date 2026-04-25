"""Cooperative abort helper for streaming chat (AGENTS.md §5.3 ABORTED case).

The LLM client can't be "cancelled" mid-token at the HTTP level — Ollama
keeps pushing NDJSON until it decides to stop. What we *can* do cheaply is
have the **reader** bail out early: this :class:`AbortContext` is the
handshake between the "producer" side (chat service reading from the LLM)
and the "listener" side (WebSocket reader loop waiting for an abort message
from the client).

Separating this out from :mod:`asyncio.Event` directly lets us grow the
type later (abort reason, timestamp, …) without touching call sites.

Lives under ``core/`` so :class:`core.chat_service.ChatService` can depend
on it without violating AGENTS.md §3 (core must not import api).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

__all__ = ["AbortContext"]


@dataclass(slots=True)
class AbortContext:
    """One-shot "please stop" signal. ``abort()`` is idempotent."""

    _event: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def aborted(self) -> bool:
        return self._event.is_set()

    def abort(self) -> None:
        self._event.set()

    async def wait(self) -> None:
        """Block until :meth:`abort` is called. Useful inside ``asyncio.wait``."""
        await self._event.wait()
