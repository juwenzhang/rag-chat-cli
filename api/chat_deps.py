"""FastAPI dependencies for chat services.

The actual builders live in :mod:`service.chat.factory` so the service layer
stays independent from FastAPI and the HTTP entrypoint.
"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.deps import get_current_user, get_session_factory
from service.chat.factory import build_chat_service, build_chat_service_for_user
from service.chat.service import ChatService
from service.db.models import User

__all__ = ["get_chat_service", "get_chat_service_for_user"]


def get_chat_service() -> ChatService:
    """Legacy FastAPI dep returning a file-backed chat service."""
    return build_chat_service()


async def get_chat_service_for_user(
    user: User = Depends(get_current_user),  # noqa: B008 - FastAPI dependency marker
    session_factory: async_sessionmaker[AsyncSession] = Depends(  # noqa: B008 - FastAPI dependency marker
        get_session_factory
    ),
) -> ChatService:
    """Primary FastAPI dep for authenticated chat routes."""
    return await build_chat_service_for_user(user=user, session_factory=session_factory)
