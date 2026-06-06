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

    Context management is wired by default — a :class:`CharApproxTokenizer`
    plus a :class:`TokenBudget` driven from
    :attr:`settings.chat.context_max_tokens`. When that value is ``0`` the
    helpers degrade to a no-op (legacy behaviour). A
    :class:`HistorySummarizer` is attached so multi-turn ReAct traces
    that overflow the budget collapse old turns into a summary instead
    of returning the "no final answer" fallback.

    The caller **must** ``await service.aclose()`` afterwards.
    """
    from service.chat.history import HistorySummarizer
    from service.chat.tokens import CharApproxTokenizer, TokenBudget
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

    # ------------------------------------------------------------------
    # Context-window plumbing
    # ------------------------------------------------------------------
    tokenizer = CharApproxTokenizer()
    budget: TokenBudget | None = None
    summarizer: HistorySummarizer | None = None
    if settings.chat.context_max_tokens > 0:
        budget = TokenBudget(
            max_tokens=settings.chat.context_max_tokens,
            reserve_for_reply=settings.chat.context_reserve_for_reply,
        )
        summarizer = HistorySummarizer(
            llm=llm,
            tokenizer=tokenizer,
            keep_recent=settings.chat.keep_recent_turns,
        )

    return ChatService(
        llm=llm,
        memory=memory,
        knowledge=kb,
        tools=tools,
        tokenizer=tokenizer,
        token_budget=budget,
        summarizer=summarizer,
    )
