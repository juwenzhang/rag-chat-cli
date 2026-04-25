"""WebSocket chat smoke + auth + abort.

Uses Starlette's sync ``TestClient`` (WebSocket support in async `httpx` is
still limited). The ``api_app`` fixture is async-built, so we wrap the
sync TestClient calls in ``asyncio.to_thread`` to keep the test loop happy.
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.testclient import TestClient


async def _register_and_login(client: object) -> str:
    """Helper: mint a fresh user and return its access token."""
    import uuid as _uuid

    email = f"ws-{_uuid.uuid4().hex[:8]}@example.com"
    password = "hunter2password"
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/register",
        json={"email": email, "password": password, "display_name": "ws"},
    )
    assert r.status_code == 201, r.text
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200
    return str(r.json()["access_token"])


async def _create_session(client: object, token: str) -> str:
    r = await client.post(  # type: ignore[attr-defined]
        "/chat/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "ws"},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _ws_happy_path(app: object, token: str, sid: str) -> list[dict[str, object]]:
    """Synchronous WS round-trip. Wrapped via asyncio.to_thread from the caller."""
    events: list[dict[str, object]] = []
    with TestClient(app) as tc, tc.websocket_connect(f"/ws/chat?token={token}") as ws:  # type: ignore[arg-type]
        ws.send_json({"type": "user_message", "session_id": sid, "content": "hi"})
        while True:
            try:
                msg = ws.receive_json()
            except Exception:
                break
            events.append(msg)
            if msg.get("type") in ("done", "error"):
                break
    return events


async def test_ws_happy_path(client: object, api_app: object) -> None:
    token = await _register_and_login(client)
    sid = await _create_session(client, token)

    events = await asyncio.to_thread(_ws_happy_path, api_app, token, sid)

    # 3 token events from FakeLLM + one terminator.
    tokens = [e for e in events if e.get("type") == "token"]
    dones = [e for e in events if e.get("type") == "done"]
    assert len(tokens) == 3
    assert len(dones) == 1
    assert "".join(str(e["delta"]) for e in tokens) == "hello world!"


async def test_ws_rejects_missing_token(api_app: object) -> None:
    def _connect_no_token() -> int:
        with TestClient(api_app) as tc:  # type: ignore[arg-type]
            try:
                with tc.websocket_connect("/ws/chat"):
                    pass
            except Exception as exc:
                # Starlette raises WebSocketDisconnect(code=...) when the
                # server closes during handshake.
                code = getattr(exc, "code", None)
                return int(code) if code else -1
        return 0

    code = await asyncio.to_thread(_connect_no_token)
    assert code == 4401


async def test_ws_abort(client: object, api_app: object) -> None:
    """Sending `{"type":"abort"}` must short-circuit the stream with ABORTED."""
    # Slow LLM so we have time to abort before it finishes.
    from api.chat_service import get_chat_service, get_chat_service_for_user
    from core.chat_service import ChatService
    from core.memory.chat_memory import FileChatMemory
    from tests.api._fakes import FakeLLM

    # Override to a slow LLM for this test only.
    def _slow_service() -> ChatService:
        import tempfile

        return ChatService(
            llm=FakeLLM(
                deltas=["a", "b", "c", "d", "e", "f", "g", "h"],
                per_token_delay=0.05,
            ),
            memory=FileChatMemory(root=tempfile.mkdtemp()),
        )

    # WS route depends on `get_chat_service_for_user`; override both aliases
    # so whichever FastAPI picks resolves to our slow service.
    api_app.dependency_overrides[get_chat_service] = _slow_service  # type: ignore[attr-defined]
    api_app.dependency_overrides[get_chat_service_for_user] = _slow_service  # type: ignore[attr-defined]
    try:
        token = await _register_and_login(client)
        sid = await _create_session(client, token)

        def _run() -> list[dict[str, object]]:
            events: list[dict[str, object]] = []
            with (
                TestClient(api_app) as tc,  # type: ignore[arg-type]
                tc.websocket_connect(f"/ws/chat?token={token}") as ws,
            ):
                ws.send_json(
                    {
                        "type": "user_message",
                        "session_id": sid,
                        "content": "hi",
                    }
                )
                # Pull two tokens, then ask the server to abort.
                events.append(ws.receive_json())
                events.append(ws.receive_json())
                ws.send_json({"type": "abort"})
                # Drain until we see an error OR the socket closes.
                try:
                    while True:
                        msg = ws.receive_json()
                        events.append(msg)
                        if msg.get("type") == "error":
                            break
                except Exception:
                    pass
            return events

        events = await asyncio.to_thread(_run)
        assert any(e.get("type") == "error" and e.get("code") == "ABORTED" for e in events), events
        # We must NOT have seen a done event — abort was earlier.
        assert not any(e.get("type") == "done" for e in events)
    finally:
        api_app.dependency_overrides.pop(get_chat_service, None)  # type: ignore[attr-defined]


@pytest.mark.parametrize("header_order", [("bearer", "{tok}"), ("{tok}", "bearer")])
async def test_ws_subprotocol_auth(
    client: object, api_app: object, header_order: tuple[str, str]
) -> None:
    """The ``Sec-WebSocket-Protocol: bearer, <token>`` form must be accepted."""
    token = await _register_and_login(client)
    await _create_session(client, token)

    subproto = ", ".join(h.format(tok=token) for h in header_order)
    accepted: list[bool] = []

    def _run() -> None:
        try:
            with (
                TestClient(api_app) as tc,  # type: ignore[arg-type]
                tc.websocket_connect(
                    "/ws/chat",
                    subprotocols=[h.format(tok=token) for h in header_order],
                ),
            ):
                accepted.append(True)
        except Exception as exc:
            code = getattr(exc, "code", None)
            # Only the "bearer, <tok>" order is expected to succeed.
            accepted.append(False)
            if header_order == ("bearer", "{tok}"):
                raise AssertionError(
                    f"bearer-subprotocol handshake failed: code={code!r} "
                    f"exc={exc!r} subproto={subproto!r}"
                ) from exc

    await asyncio.to_thread(_run)
    if header_order == ("bearer", "{tok}"):
        assert accepted == [True]
