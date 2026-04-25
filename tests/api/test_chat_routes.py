"""Chat session CRUD + cross-user isolation.

The streaming ``POST /chat/messages`` exercises :class:`ChatService` which
talks to a real Ollama process. Here we focus on the session / message
bookkeeping; the stream path is covered by Change 7 with a mocked LLM.
"""

from __future__ import annotations

import pytest


async def test_require_auth_for_sessions(client: object) -> None:
    r = await client.get("/chat/sessions")  # type: ignore[attr-defined]
    assert r.status_code == 401


async def test_create_and_list_sessions(client: object, auth_headers: dict[str, str]) -> None:
    r = await client.post(  # type: ignore[attr-defined]
        "/chat/sessions",
        headers=auth_headers,
        json={"title": "first"},
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = await client.get("/chat/sessions", headers=auth_headers)  # type: ignore[attr-defined]
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == sid


async def test_messages_404_when_session_not_owned(
    client: object, auth_headers: dict[str, str]
) -> None:
    # Register a second user and create a session under them…
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/register",
        json={"email": "other@example.com", "password": "hunter2password"},
    )
    assert r.status_code == 201

    r = await client.post(  # type: ignore[attr-defined]
        "/auth/login",
        json={"email": "other@example.com", "password": "hunter2password"},
    )
    other_token = r.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    r = await client.post(  # type: ignore[attr-defined]
        "/chat/sessions",
        headers=other_headers,
        json={"title": "secret"},
    )
    other_sid = r.json()["id"]

    # …and verify the *first* user gets 404 when querying its messages.
    r = await client.get(  # type: ignore[attr-defined]
        f"/chat/sessions/{other_sid}/messages",
        headers=auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.parametrize("bad_uuid", ["not-a-uuid", "123"])
async def test_messages_with_invalid_uuid_is_422(
    client: object, auth_headers: dict[str, str], bad_uuid: str
) -> None:
    r = await client.get(  # type: ignore[attr-defined]
        f"/chat/sessions/{bad_uuid}/messages",
        headers=auth_headers,
    )
    assert r.status_code == 422
