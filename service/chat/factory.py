"""Factory for per-request :class:`service.chat.service.ChatService`.

Framework-agnostic builder: takes plain Python inputs (a SQLAlchemy session
factory + a user) and assembles a :class:`ChatService` with the production
DB-backed memory and pgvector retriever. FastAPI ``Depends`` wrappers live
in :mod:`api.chat_deps` so this module stays free of HTTP concerns.

The returned service is **not** a yield-style dep on purpose: SSE / WS
routes need to keep the :class:`ChatService` alive for the full duration
of the stream. Each route owns ``await service.aclose()`` in its own
``finally`` block.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from service.chat.service import ChatService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from service.db.models import User

__all__ = ["build_chat_service_for_user"]


async def build_chat_service_for_user(
    *,
    user: User,
    session_factory: async_sessionmaker[AsyncSession],
) -> ChatService:
    """DB-backed :class:`ChatService` scoped to ``user``.

    Memory is :class:`DbChatMemory` (chat_sessions / messages tables),
    retriever is :class:`PgvectorKnowledgeBase` (when retrieval is enabled),
    LLM is resolved from the user's :class:`Provider` registry with a
    fallback to the legacy ``OLLAMA_*`` / ``OPENAI_*`` env settings.

    The caller **must** ``await service.aclose()`` afterwards.
    """
    from service.knowledge import KnowledgeBase, PgvectorKnowledgeBase
    from service.memory.chat_memory import DbChatMemory
    from service.providers.runtime import build_llm_for_user
    from service.tools.factory import build_builtin_tool_registry
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
    tools = build_builtin_tool_registry(ollama_api_key=lambda: getattr(llm, "api_key", None))
    return ChatService(llm=llm, memory=memory, knowledge=kb, tools=tools)
