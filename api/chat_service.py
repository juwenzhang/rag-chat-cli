"""Factory for per-request :class:`core.chat_service.ChatService`.

Two flavours of factory live here:

* :func:`build_chat_service` — file-backed memory. Used only by tests /
  offline scripts. The corresponding FastAPI dep is :func:`get_chat_service`
  (kept around so existing test fixtures keep working via dependency
  overrides without change).

* :func:`build_chat_service_for_user` — **DB-backed memory** bound to a
  specific user. This is what the three authenticated streaming /
  non-streaming chat routes actually use. The FastAPI dep is
  :func:`get_chat_service_for_user`.

Neither factory is a yield-style dependency on purpose: SSE / WS routes need
to keep the :class:`ChatService` alive for the full duration of the stream,
which is incompatible with FastAPI's "close the dep at the end of the
handler" semantics. Each route is responsible for ``await service.aclose()``
inside its own ``finally`` block.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Depends

from api.deps import get_current_user, get_session_factory
from core.chat_service import ChatService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from db.models import User

__all__ = [
    "build_chat_service",
    "build_chat_service_for_user",
    "get_chat_service",
    "get_chat_service_for_user",
]


def build_chat_service() -> ChatService:
    """Return a fresh file-backed :class:`ChatService` wired to global settings.

    Used by tests (via dependency override) and by the CLI's offline /
    unauthenticated code path. Production HTTP/WS routes go through
    :func:`build_chat_service_for_user` instead.

    The caller **must** ``await service.aclose()`` afterwards.
    """
    # Imports are local on purpose: the ``api`` package should stay importable
    # from harnesses that don't ship the LLM runtime.
    from core.knowledge.base import FileKnowledgeBase
    from core.llm.ollama import OllamaClient
    from core.memory.chat_memory import FileChatMemory
    from settings import settings

    llm = OllamaClient.from_settings(settings)
    memory = FileChatMemory.from_settings(settings)
    kb = FileKnowledgeBase.from_settings(settings) if settings.retrieval.enabled else None
    return ChatService(llm=llm, memory=memory, knowledge=kb)


def build_chat_service_for_user(
    user: User = Depends(get_current_user),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ChatService:
    """Return a DB-backed :class:`ChatService` whose memory is scoped to ``user``.

    This is the primary production factory — REST / SSE / WS routes all use
    it so a user's history is persisted into ``chat_sessions`` /
    ``messages`` and is shared across clients (Web + CLI + future iOS).

    The caller **must** ``await service.aclose()`` afterwards.
    """
    from core.knowledge.base import FileKnowledgeBase
    from core.llm.ollama import OllamaClient
    from core.memory.chat_memory import DbChatMemory
    from settings import settings

    llm = OllamaClient.from_settings(settings)
    memory = DbChatMemory(session_factory=session_factory, user_id=user.id)
    kb = FileKnowledgeBase.from_settings(settings) if settings.retrieval.enabled else None
    return ChatService(llm=llm, memory=memory, knowledge=kb)


# ---------------------------------------------------------------------------
# FastAPI dep aliases — tests override these with a fake ChatService.
# ---------------------------------------------------------------------------


def get_chat_service() -> ChatService:
    """Legacy dep — returns a file-backed service. Used as the default
    override target in test fixtures."""
    return build_chat_service()


def get_chat_service_for_user(
    user: User = Depends(get_current_user),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> ChatService:
    """Primary FastAPI dep for authenticated chat routes. Wraps
    :func:`build_chat_service_for_user` so tests can override it."""
    return build_chat_service_for_user(user=user, session_factory=session_factory)
