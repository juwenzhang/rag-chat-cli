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
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("AUTH_BCRYPT_ROUNDS", "4")

    from importlib import reload

    import settings as settings_mod

    reload(settings_mod)

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

    memory_root = tmp_path_factory.mktemp("chat_mem")

    def _override_chat_service() -> ChatService:
        from tests.api._fakes import FakeLLM

        memory = FileChatMemory(root=memory_root)
        return ChatService(llm=FakeLLM(), memory=memory)

    from db.session import dispose_engine, init_engine

    await dispose_engine()
    init_engine("sqlite+aiosqlite:///:memory:")
    import db.session as _db_session

    _db_session._engine = async_engine  # type: ignore[assignment]
    _db_session._SessionLocal = sf  # type: ignore[assignment]

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
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=api_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def registered_user(client: object) -> dict[str, str]:
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
    resp = await client.post(  # type: ignore[attr-defined]
        "/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
