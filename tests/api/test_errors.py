"""Global exception handler shape checks."""

from __future__ import annotations


async def test_404_envelope(client: object) -> None:
    r = await client.get("/nope")  # type: ignore[attr-defined]
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "HTTP_404"
    assert "message" in body
    assert "request_id" in body


async def test_invalid_token_is_401(client: object) -> None:
    r = await client.get(  # type: ignore[attr-defined]
        "/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401


async def test_error_envelope_carries_request_id(client: object) -> None:
    r = await client.get(  # type: ignore[attr-defined]
        "/me",
        headers={
            "Authorization": "Bearer not-a-real-token",
            "X-Request-ID": "err-req-123",
        },
    )
    assert r.status_code == 401
    body = r.json()
    assert body["request_id"] == "err-req-123"


async def test_500_envelope_carries_request_id(api_app: object) -> None:
    """Regression for the 'request_id: null on 500' bug.

    ``BaseHTTPMiddleware`` runs the route in a sub-task; our ``finally:
    ContextVar.reset(...)`` clears the ID before the global handler runs.
    The fix stashes the ID on ``request.state``; this test guards it.

    Uses a dedicated ``AsyncClient`` with ``raise_app_exceptions=False`` so
    the 500 surfaces as an HTTP response rather than re-raising in the test.
    """
    from httpx import ASGITransport, AsyncClient

    # Mount a one-off route that always blows up.
    @api_app.get("/__boom")  # type: ignore[attr-defined]
    async def _boom() -> None:
        raise RuntimeError("kaboom")

    transport = ASGITransport(app=api_app, raise_app_exceptions=False)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        r = await c.get("/__boom", headers={"X-Request-ID": "five-hundred-trace"})

    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "INTERNAL"
    assert body["request_id"] == "five-hundred-trace"
    # And the response header echoes it too.
    assert r.headers.get("X-Request-ID") == "five-hundred-trace"
