"""Runtime provider resolution — used by the chat service factory.

The provider for the current request resolves through this chain (first
non-null wins):

1. ``user_preferences.default_provider_id`` for ``user_id``
2. First :class:`db.models.Provider` row owned by ``user_id``
   (ordered by ``is_default DESC, name ASC``)
3. Built-in :mod:`settings`-driven defaults (legacy ``OLLAMA_*`` / ``OPENAI_*``
   env vars). This keeps the API usable for users who have not yet
   onboarded any providers via the new endpoints.

The model resolves through a separate chain (handlers consult
:func:`resolve_session_model`):

1. ``chat_sessions.model`` for the request's session (per-session pin)
2. ``user_preferences.default_model``
3. ``None`` — the LLM client falls back to its own ``chat_model`` default.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from core.providers import decrypt_api_key
from db.models import ChatSession, Provider, UserPreference

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from core.llm.client import LLMClient

logger = logging.getLogger(__name__)

__all__ = [
    "build_llm_for_user",
    "resolve_session_model",
]


async def build_llm_for_user(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> tuple[LLMClient, str | None]:
    """Pick the right :class:`LLMClient` for ``user_id``.

    Returns a ``(client, default_model_pref)`` tuple. ``default_model_pref``
    is the user's preference-level model name (may be ``None``); handlers
    decide whether to override it per session via
    :func:`resolve_session_model`.

    The returned client owns an ``httpx.AsyncClient`` — caller must
    ``await client.aclose()`` when done. :class:`core.chat_service.ChatService`
    does this in its own ``aclose`` for routes that hold the service.
    """
    # Imports here so the legacy settings-only fallback path doesn't drag
    # ORM modules into ``core.chat_service`` unconditionally.
    from core.llm.ollama import OllamaClient
    from core.llm.openai import OpenAIClient
    from settings import settings

    async with session_factory() as session:
        provider = await _pick_provider(session, user_id=user_id)
        pref = await session.get(UserPreference, user_id)
        default_model = pref.default_model if pref is not None else None

    if provider is None:
        # No user-managed provider — fall back to env-configured Ollama
        # (or OpenAI when only OPENAI_API_KEY is set). Preserves the
        # pre-Sprint-2 behaviour for users who have not onboarded.
        logger.debug("user %s has no Provider rows — using env-configured fallback", user_id)
        if settings.openai.api_key and not settings.ollama.base_url:
            return OpenAIClient.from_settings(settings), default_model
        return OllamaClient.from_settings(settings), default_model

    api_key = decrypt_api_key(provider.api_key_encrypted)
    if provider.type == "ollama":
        return (
            OllamaClient(
                base_url=provider.base_url,
                chat_model=default_model or settings.ollama.chat_model,
                embed_model=settings.ollama.embed_model,
                timeout=float(settings.ollama.timeout),
                api_key=api_key,
            ),
            default_model,
        )
    if provider.type == "openai":
        return (
            OpenAIClient(
                base_url=provider.base_url,
                chat_model=default_model or settings.openai.chat_model,
                embed_model=settings.openai.embed_model,
                api_key=api_key,
                timeout=float(settings.openai.timeout),
                organization=settings.openai.organization,
            ),
            default_model,
        )
    raise RuntimeError(f"unsupported provider type stored in DB: {provider.type!r}")


async def _pick_provider(
    session: AsyncSession, *, user_id: uuid.UUID
) -> Provider | None:
    """Return the provider to use for ``user_id``, or ``None``."""
    pref = await session.get(UserPreference, user_id)
    if pref is not None and pref.default_provider_id is not None:
        chosen = await session.get(Provider, pref.default_provider_id)
        if chosen is not None and chosen.user_id == user_id and chosen.enabled:
            return chosen
        # Stale pointer — fall through to "first owned".

    return await session.scalar(
        select(Provider)
        .where(Provider.user_id == user_id, Provider.enabled.is_(True))
        .order_by(Provider.is_default.desc(), Provider.name.asc())
        .limit(1)
    )


async def resolve_session_model(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    default_model: str | None,
) -> str | None:
    """Resolve the effective model for one chat session.

    ``default_model`` is the user's preference-level default (typically
    returned by :func:`build_llm_for_user`). The per-session pin
    (``chat_sessions.model``) overrides it.

    Caller must own ``session_id`` — that check belongs to the route, not
    here. Returns ``None`` only when neither the session nor the
    preferences have a model pinned, signalling "let the client use its
    own configured default".
    """
    row = await session.get(ChatSession, session_id)
    if row is not None and row.user_id == user_id and row.model:
        return row.model
    return default_model
