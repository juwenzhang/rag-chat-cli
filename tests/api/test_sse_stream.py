"""End-to-end SSE smoke (deterministic FakeLLM)."""

from __future__ import annotations

import json


def _parse_sse(blob: bytes) -> list[dict[str, object]]:
    """Crack a raw SSE response body into ``[{type, data}]`` dicts."""
    frames: list[dict[str, object]] = []
    for chunk in blob.split(b"\n\n"):
        chunk = chunk.strip()
        if not chunk or chunk.startswith(b":"):
            continue  # keepalive / empty
        event_name: str | None = None
        data_parts: list[str] = []
        for raw_line in chunk.split(b"\n"):
            line = raw_line.decode("utf-8")
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data_parts.append(line[len("data: ") :])
        if event_name is None:
            continue
        parsed = json.loads("".join(data_parts))
        parsed.setdefault("__event__", event_name)
        frames.append(parsed)
    return frames


async def test_stream_requires_auth(client: object) -> None:
    r = await client.post(  # type: ignore[attr-defined]
        "/chat/stream",
        json={
            "session_id": "00000000-0000-0000-0000-000000000000",
            "content": "hi",
        },
    )
    assert r.status_code == 401


async def test_stream_session_not_found(client: object, auth_headers: dict[str, str]) -> None:
    r = await client.post(  # type: ignore[attr-defined]
        "/chat/stream",
        headers=auth_headers,
        json={
            "session_id": "00000000-0000-0000-0000-000000000000",
            "content": "hi",
        },
    )
    assert r.status_code == 404


async def test_stream_happy_path_emits_token_and_done(
    client: object, auth_headers: dict[str, str]
) -> None:
    # First create a session via the REST API.
    r = await client.post(  # type: ignore[attr-defined]
        "/chat/sessions", headers=auth_headers, json={"title": "s"}
    )
    assert r.status_code == 201
    sid = r.json()["id"]

    r = await client.post(  # type: ignore[attr-defined]
        "/chat/stream",
        headers=auth_headers,
        json={"session_id": sid, "content": "hi"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(r.content)
    # FakeLLM yields 3 deltas → 3 token events + 1 done.
    token_events = [e for e in events if e["__event__"] == "token"]
    done_events = [e for e in events if e["__event__"] == "done"]
    assert len(token_events) == 3
    assert len(done_events) == 1
    # Aggregated text matches the fake's script.
    assert "".join(str(e["delta"]) for e in token_events) == "hello world!"
