"""End-to-end auth flow: register → login → /me → refresh → logout."""

from __future__ import annotations


async def test_register_login_me_refresh_logout(client: object) -> None:
    email = "flow@example.com"
    password = "password1flow"

    # 1. Register
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/register",
        json={"email": email, "password": password, "display_name": "Flow"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["email"] == email

    # 2. Register duplicate → 409
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/register",
        json={"email": email, "password": password},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "EMAIL_EXISTS"

    # 3. Wrong password → 401
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/login",
        json={"email": email, "password": "wrongpassword1"},
    )
    assert r.status_code == 401
    assert r.json()["code"] == "INVALID_CREDENTIALS"

    # 4. Correct login → 200 with tokens
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200
    tokens = r.json()
    assert tokens["access_token"] and tokens["refresh_token"]

    # 5. /me with bearer → 200
    r = await client.get(  # type: ignore[attr-defined]
        "/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["email"] == email

    # 6. Refresh rotates
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert r.status_code == 200
    rotated = r.json()
    assert rotated["access_token"] != tokens["access_token"]
    assert rotated["refresh_token"] != tokens["refresh_token"]

    # 7. Replay old refresh → 401 reuse detected
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert r.status_code == 401
    assert r.json()["code"] == "TOKEN_REUSE_DETECTED"

    # 8. Fresh login → logout OK
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/login",
        json={"email": email, "password": password},
    )
    new_tokens = r.json()
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert r.status_code == 204


async def test_register_validation_422(client: object) -> None:
    # Password too short — pydantic rejects.
    r = await client.post(  # type: ignore[attr-defined]
        "/auth/register",
        json={"email": "x@y.com", "password": "short"},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


async def test_me_without_token_is_401(client: object) -> None:
    r = await client.get("/me")  # type: ignore[attr-defined]
    assert r.status_code == 401
