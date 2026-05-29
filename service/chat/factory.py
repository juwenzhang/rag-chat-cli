"""Factory for per-request :class:`service.chat.service.ChatService`.

This module is intentionally framework-agnostic: it builds chat services from
plain Python inputs and must not import FastAPI or the HTTP layer. FastAPI
``Depends`` wrappers live in :mod:`api.chat_deps`.

Neither factory is a yield-style dependency on purpose: SSE / WS routes need
to keep the :class:`ChatService` alive for the full duration of the stream,
which is incompatible with FastAPI's "close the dep at the end of the
handler" semantics. Each route is responsible for ``await service.aclose()``
inside its own ``finally`` block.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from service.chat.service import ChatService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from service.db.models import User

__all__ = [
    "build_chat_service",
    "build_chat_service_for_user",
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
    from service.knowledge import FileKnowledgeBase, KnowledgeBase
    from service.llm.ollama import OllamaClient
    from service.memory.chat_memory import FileChatMemory
    from settings import settings

    llm = OllamaClient.from_settings(settings)
    memory = FileChatMemory.from_settings(settings)
    kb: KnowledgeBase | None = (
        FileKnowledgeBase.from_settings(llm=llm, s=settings) if settings.retrieval.enabled else None
    )
    return ChatService(llm=llm, memory=memory, knowledge=kb)


async def build_chat_service_for_user(
    *,
    user: User,
    session_factory: async_sessionmaker[AsyncSession],
) -> ChatService:
    """Return a DB-backed :class:`ChatService` whose memory is scoped to ``user``.

    This is the primary production factory — REST / SSE / WS routes all use
    it so a user's history is persisted into ``chat_sessions`` /
    ``messages`` and is shared across clients (Web + CLI + future iOS).
    Retrieval here is the real :class:`PgvectorKnowledgeBase` (#9 P2.1)
    scoped to the requesting user (their own documents + shared).

    LLM client is resolved from the user's :class:`db.models.Provider`
    registry (Sprint 2), falling back to legacy ``OLLAMA_*`` /
    ``OPENAI_*`` settings when the user has none configured.

    The caller **must** ``await service.aclose()`` afterwards.
    """
    from service.knowledge import KnowledgeBase, PgvectorKnowledgeBase
    from service.memory.chat_memory import DbChatMemory
    from service.providers.runtime import build_llm_for_user
    from settings import settings

    llm, _default_model = await build_llm_for_user(session_factory, user.id)
    memory = DbChatMemory(session_factory=session_factory, user_id=user.id)
    kb: KnowledgeBase | None = (
        PgvectorKnowledgeBase.from_settings(
            session_factory=session_factory,
            llm=llm,
            user_id=user.id,
            s=settings,
        )
        if settings.retrieval.enabled
        else None
    )
    return ChatService(llm=llm, memory=memory, knowledge=kb)
