"""FastAPI application factory (AGENTS.md §2, §5).

`create_app()` is the single public entry point: `uvicorn` loads it with
``--factory``, tests call it directly with an override-friendly `Settings`
instance. It intentionally stays small — middleware wiring, exception
handlers, router inclusion, and a lifespan that owns the DB engine.

Two HTTP surfaces share the same routers (see
``docs/backend/MULTI_CLIENT_AUTH_DESIGN.md``):

* ``/`` — the legacy browser surface. Strict ``APP_CORS_ORIGINS`` allowlist,
  no ``X-Client-Id`` requirement, used by ``websites/``.
* ``/v1/*`` — the non-browser surface mounted as a sub-app. Wide-open CORS
  (Bearer-only, no cookie credentials cross site) and a mandatory
  ``X-Client-Id`` header. Used by ``clients/tui`` (and any future mobile /
  IDE / agent clients).

Mounting routers on both surfaces keeps the operational story simple: any
router file is a single source of truth, and reverse proxies / WAFs can
target a path prefix instead of sniffing user agents.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.middleware.client_id import ClientIdMiddleware
from api.middleware.errors import install_exception_handlers
from api.middleware.logging import AccessLogMiddleware
from api.middleware.path_cors import PathFilteredCORSMiddleware
from api.middleware.request_id import RequestIDMiddleware
from api.routers import assets as assets_router
from api.routers import auth as auth_router
from api.routers import bookmarks as bookmarks_router
from api.routers import chat as chat_router
from api.routers import chat_stream as chat_stream_router
from api.routers import chat_ws as chat_ws_router
from api.routers import health as health_router
from api.routers import knowledge as knowledge_router
from api.routers import me as me_router
from api.routers import orgs as orgs_router
from api.routers import providers as providers_router
from api.routers import shares as shares_router
from api.routers import wiki as wiki_router

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
    from service.db.session import dispose_engine, init_engine

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


def _register_routers(app: FastAPI) -> None:
    """Mount every router on the given app/sub-app.

    Called once for the root app and once for the ``/v1`` sub-app so the
    same set of endpoints answers both surfaces. Any new router belongs
    here — adding it on the root app only is the easy mistake.
    """
    app.include_router(health_router.router)
    app.include_router(auth_router.router, prefix="/auth")
    app.include_router(me_router.router)
    app.include_router(chat_router.router, prefix="/chat")
    # SSE stream lives under /chat alongside the non-streaming sibling.
    app.include_router(chat_stream_router.router, prefix="/chat")
    # WebSocket route is at /ws/chat (no extra prefix, see chat_ws.router).
    app.include_router(chat_ws_router.router)
    app.include_router(knowledge_router.router, prefix="/knowledge")
    app.include_router(assets_router.router)
    # /providers (and /providers/test, /providers/{id}/models) + /me/preferences.
    app.include_router(providers_router.router)
    # /shares (public token-based view + owner CRUD) + /bookmarks (private).
    app.include_router(shares_router.router)
    app.include_router(bookmarks_router.router)
    # /orgs (workspaces) + /wiki (BlockNote pages scoped to an org).
    app.include_router(orgs_router.router)
    app.include_router(wiki_router.router)


def _build_v1_subapp(settings: Settings) -> FastAPI:
    """Build the ``/v1`` non-browser surface.

    Differences from the root app:

    * CORS is wide open. Bearer auth carries no ambient credentials, so
      cross-origin posts can't be used as confused-deputy attacks the way
      cookie sessions can. Reverse proxies (Cloudflare, Hugging Face Space
      gateways) routinely strip / refuse the bespoke ``Origin`` browsers
      send, and we want CLIs to keep working there.
    * ``ClientIdMiddleware`` enforces the ``X-Client-Id`` allowlist. We
      could push that into a router-level dependency, but a middleware
      lets us reject unauthenticated traffic before it even hits FastAPI's
      validation pipeline.
    * Lifespan is *not* re-installed on the sub-app — Starlette only runs
      the root app's lifespan. The shared DB engine is therefore owned
      exactly once.
    """
    sub = FastAPI(
        title="rag-chat API (v1, non-browser)",
        version="0.1.0",
        # Hide the sub-app from the public schema listing — `/openapi.json`
        # on the root app already covers every route, and a duplicate entry
        # would only confuse the docs page.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # Order matters: Starlette runs the *last* `add_middleware` call first.
    # We want CORS to wrap ClientIdMiddleware so preflight ``OPTIONS``
    # requests get answered before our header check (which the browser
    # cannot satisfy on a preflight anyway).
    sub.add_middleware(
        ClientIdMiddleware,
        protected_prefixes=("/",),
        allowed_client_ids=settings.app.allowed_client_ids,
    )
    sub.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        # Bearer-only — no cookies in flight, so cross-origin posts cannot
        # be used as confused-deputy attacks. Explicit ``False`` makes the
        # intent obvious for future readers.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_exception_handlers(sub)
    _register_routers(sub)
    return sub


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
    #
    # ``PathFilteredCORSMiddleware`` skips the strict allowlist on ``/v1/*``
    # so the sub-app's wide-open CORS can answer preflights for the
    # non-browser surface — Starlette's mount semantics put the sub-app
    # *inside* the root middleware stack, which would otherwise have the
    # root CORS reject cross-origin OPTIONS before they ever reach
    # ``/v1``. See ``docs/backend/MULTI_CLIENT_AUTH_DESIGN.md``.
    app.add_middleware(
        PathFilteredCORSMiddleware,  # type: ignore[arg-type]
        excluded_prefixes=("/v1",),
        allow_origins=settings.app.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(RequestIDMiddleware, header_name=settings.app.request_id_header)
    app.add_middleware(AccessLogMiddleware)

    install_exception_handlers(app)

    if settings.storage.backend == "local":
        from pathlib import Path

        from fastapi.staticfiles import StaticFiles

        Path(settings.storage.local_root).mkdir(parents=True, exist_ok=True)
        app.mount(
            settings.storage.public_base_url,
            StaticFiles(directory=settings.storage.local_root),
            name="uploads",
        )

    # Routers on the legacy / browser surface.
    _register_routers(app)

    # Mount the non-browser surface. Sub-apps are full FastAPI instances,
    # which means routers, middleware and exception handlers are all
    # rebuilt — a deliberate isolation boundary.
    app.mount("/v1", _build_v1_subapp(settings))

    return app
