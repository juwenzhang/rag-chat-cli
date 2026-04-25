"""Fixtures for the `tests/api` package.

Key design choices:

* **In-memory SQLite**: every test gets its own engine + fresh schema via
  ``Base.metadata.create_all``. Real Postgres paths (ivfflat, JSONB queries)
  are opted into elsewhere with ``@pytest.mark.pg``.
* **Override `get_db_session`**: the app factory calls ``init_engine`` during
  lifespan, which would point at the production URL. We short-circuit that
  by flipping ``DATABASE_URL`` to ``sqlite+aiosqlite:///:memory:`` *before*
  building the app, and by overriding the session dependency to hand out
  sessions bound to the fixture-built engine.
* **httpx AsyncClient with ASGITransport**: keeps tests pure-Python — no
  socket binding, no uvicorn. Lifespan is driven through
  :class:`httpx.ASGITransport` so the app goes through proper
  startup/shutdown.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def api_app(
    async_engine: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> AsyncIterator[object]:
    """Build a :class:`FastAPI` app wired to the in-memory SQLite engine.

    Also stubs the LLM layer (:func:`api.chat_service.get_chat_service`) with
    a deterministic fake so streaming / WS tests don't need a live Ollama.
    Tests that want custom LLM behaviour call ``api_app.dependency_overrides``
    themselves to replace the stub.
    """
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    # 1. Configure settings to an in-memory DB so lifespan's init_engine is safe.
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    # 2. Speed up bcrypt for tests that exercise the full register/login path.
    monkeypatch.setenv("AUTH_BCRYPT_ROUNDS", "4")

    # Reload settings after env mutation.
    from importlib import reload

    import settings as settings_mod

    reload(settings_mod)

    # Reset password context cache so the new bcrypt_rounds takes effect.
    from core.auth import password as _pw

    _pw._context.cache_clear()

    from api.app import create_app
    from api.chat_service import get_chat_service, get_chat_service_for_user
    from api.deps import get_auth_service, get_db_session, get_session_factory
    from core.auth.service import AuthService
    from core.chat_service import ChatService
    from core.memory.chat_memory import FileChatMemory

    app = create_app(settings_mod.settings)

    assert isinstance(async_engine, AsyncEngine)
    sf = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with sf() as session:
            yield session

    def _override_auth_service() -> AuthService:
        return AuthService(sf)

    def _override_session_factory() -> async_sessionmaker[AsyncSession]:
        return sf

    # Default fake: emits three tokens then done. Tests that want something
    # different override ``get_chat_service`` again inside their own body.
    #
    # v1.2 note: the authenticated chat routes now depend on
    # ``get_chat_service_for_user`` which, in production, hands out a
    # DbChatMemory-backed service. We override it to the same fake-LLM +
    # file-backed factory so tests stay offline and deterministic.
    memory_root = tmp_path_factory.mktemp("chat_mem")

    def _override_chat_service() -> ChatService:
        from tests.api._fakes import FakeLLM  # lazy to avoid import cycles

        memory = FileChatMemory(root=memory_root)
        return ChatService(llm=FakeLLM(), memory=memory)

    # db.session's module-level engine is used by ``current_session_factory()``
    # (the auth / ws code paths). Point it at our test engine so WS auth and
    # the ws handler's ownership check both go through SQLite.
    from db.session import dispose_engine, init_engine

    await dispose_engine()  # clear any previous test's engine
    init_engine("sqlite+aiosqlite:///:memory:")
    # Replace the module-level session factory with the one bound to
    # ``async_engine`` so WS handlers see the same tables as HTTP routes.
    import db.session as _db_session

    # Poke the module-level singletons directly so ``current_session_factory()``
    # in prod code paths returns our test-bound factory. This is intentionally
    # "test surgery" — the same override via a setter would leak to prod.
    _db_session._engine = async_engine
    _db_session._SessionLocal = sf

    app.dependency_overrides[get_db_session] = _override_session
    app.dependency_overrides[get_auth_service] = _override_auth_service
    app.dependency_overrides[get_session_factory] = _override_session_factory
    app.dependency_overrides[get_chat_service] = _override_chat_service
    app.dependency_overrides[get_chat_service_for_user] = _override_chat_service

    yield app

    app.dependency_overrides.clear()
    await dispose_engine()


@pytest_asyncio.fixture
async def client(api_app: object) -> AsyncIterator[object]:
    """httpx AsyncClient bound to the test app via ASGITransport."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=api_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def registered_user(client: object) -> dict[str, str]:
    """Register a single user and return ``{"email","password"}``."""
    email = "user@example.com"
    password = "hunter2password"
    resp = await client.post(  # type: ignore[attr-defined]
        "/auth/register",
        json={"email": email, "password": password, "display_name": "User"},
    )
    assert resp.status_code == 201, resp.text
    return {"email": email, "password": password}


@pytest_asyncio.fixture
async def auth_headers(client: object, registered_user: dict[str, str]) -> dict[str, str]:
    """Return a usable ``Authorization`` header for :data:`registered_user`."""
    resp = await client.post(  # type: ignore[attr-defined]
        "/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
