"""Smoke test for the liveness probe."""

from __future__ import annotations


async def test_health_is_public(client: object) -> None:
    resp = await client.get("/health")  # type: ignore[attr-defined]
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_request_id_header_echoes(client: object) -> None:
    resp = await client.get(  # type: ignore[attr-defined]
        "/health",
        headers={"X-Request-ID": "test-abc"},
    )
    assert resp.headers.get("X-Request-ID") == "test-abc"


async def test_request_id_generated_when_missing(client: object) -> None:
    resp = await client.get("/health")  # type: ignore[attr-defined]
    rid = resp.headers.get("X-Request-ID")
    assert rid is not None and len(rid) >= 8
