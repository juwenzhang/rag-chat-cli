"""FastAPI application factory (AGENTS.md §2, §5).

`create_app()` is the single public entry point: `uvicorn` loads it with
``--factory``, tests call it directly with an override-friendly `Settings`
instance. It intentionally stays small — middleware wiring, exception
handlers, router inclusion, and a lifespan that owns the DB engine.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.middleware.errors import install_exception_handlers
from api.middleware.logging import AccessLogMiddleware
from api.middleware.request_id import RequestIDMiddleware
from api.routers import auth as auth_router
from api.routers import chat as chat_router
from api.routers import chat_stream as chat_stream_router
from api.routers import chat_ws as chat_ws_router
from api.routers import health as health_router
from api.routers import knowledge as knowledge_router
from api.routers import me as me_router
from api.routers import providers as providers_router

if TYPE_CHECKING:
    from settings import Settings

__all__ = ["create_app"]

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the DB engine lifecycle for the life of the ASGI app.

    ``init_engine`` is idempotent — calling it twice inside the same process
    (e.g. under uvicorn's reload loop) simply returns the existing engine.
    """
    from db.session import dispose_engine, init_engine

    settings: Settings = app.state.settings
    init_engine(settings.db.database_url, echo=settings.db.echo_sql)
    try:
        yield
    finally:
        await dispose_engine()


_TAG_DESCRIPTIONS = [
    {"name": "meta", "description": "Liveness / diagnostics."},
    {"name": "auth", "description": "Registration, login, JWT rotation."},
    {"name": "me", "description": "Authenticated user self-service."},
    {"name": "chat", "description": "Chat sessions and messages (non-streaming)."},
    {"name": "knowledge", "description": "Document upload and retrieval (stubs until RAG lands)."},
]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a ready-to-serve :class:`FastAPI` app.

    Passing ``settings`` lets tests inject a stripped-down configuration
    without mutating the module singleton. When omitted we fall back to the
    global :data:`settings.settings`.
    """
    if settings is None:
        from settings import settings as default_settings

        settings = default_settings

    app = FastAPI(
        title="rag-chat API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        openapi_tags=_TAG_DESCRIPTIONS,
        lifespan=_lifespan,
    )
    app.state.settings = settings

    # Middleware — outer-most first. Request-ID must wrap logging so the ID
    # is already in the context var when we write the access line.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RequestIDMiddleware, header_name=settings.app.request_id_header)
    app.add_middleware(AccessLogMiddleware)

    install_exception_handlers(app)

    # Routers. ``health`` has no prefix; the others are namespaced per §5.
    app.include_router(health_router.router)
    app.include_router(auth_router.router, prefix="/auth")
    app.include_router(me_router.router)
    app.include_router(chat_router.router, prefix="/chat")
    # SSE stream lives under /chat alongside the non-streaming sibling.
    app.include_router(chat_stream_router.router, prefix="/chat")
    # WebSocket route is at /ws/chat (no extra prefix, see chat_ws.router).
    app.include_router(chat_ws_router.router)
    app.include_router(knowledge_router.router, prefix="/knowledge")
    # /providers (and /providers/test, /providers/{id}/models) + /me/preferences.
    app.include_router(providers_router.router)

    return app
