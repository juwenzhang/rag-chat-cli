"""``/me`` PATCH behaviour — whitelisted fields only."""

from __future__ import annotations


async def test_patch_display_name(client: object, auth_headers: dict[str, str]) -> None:
    r = await client.patch(  # type: ignore[attr-defined]
        "/me",
        headers=auth_headers,
        json={"display_name": "Renamed"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == "Renamed"


async def test_patch_rejects_unknown_fields(client: object, auth_headers: dict[str, str]) -> None:
    # Unknown fields are silently ignored by pydantic's default behaviour,
    # so the endpoint returns 200 but does NOT touch the ignored column.
    r = await client.patch(  # type: ignore[attr-defined]
        "/me",
        headers=auth_headers,
        json={"email": "hacker@example.com"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "user@example.com"
