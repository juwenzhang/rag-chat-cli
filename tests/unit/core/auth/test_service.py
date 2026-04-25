"""Unit tests for core.auth.service — register / login / refresh / logout."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from core.auth.service import AuthService


async def test_register_creates_user(auth_service: object) -> None:
    svc = cast("AuthService", auth_service)

    user = await svc.register("Alice@Example.com", "hunter123", display_name="Alice")
    assert user.email == "alice@example.com"  # lower-cased
    assert user.display_name == "Alice"
    assert user.hashed_password != "hunter123"


async def test_register_duplicate_email_raises(auth_service: object) -> None:
    from core.auth.errors import EmailAlreadyExistsError

    svc = cast("AuthService", auth_service)
    await svc.register("a@b.com", "password1")
    with pytest.raises(EmailAlreadyExistsError):
        await svc.register("A@B.COM", "other-pw-2")


async def test_login_happy_path_returns_pair(auth_service: object) -> None:
    svc = cast("AuthService", auth_service)
    await svc.register("bob@example.com", "correcthorse1")

    pair = await svc.login("bob@example.com", "correcthorse1")
    assert pair.access_token
    assert pair.refresh_token
    assert pair.access_expires_at < pair.refresh_expires_at


async def test_login_wrong_password_raises(auth_service: object) -> None:
    from core.auth.errors import InvalidCredentialsError

    svc = cast("AuthService", auth_service)
    await svc.register("c@d.com", "rightpass1")

    with pytest.raises(InvalidCredentialsError):
        await svc.login("c@d.com", "wrongpass9")


async def test_login_unknown_email_raises(auth_service: object) -> None:
    from core.auth.errors import InvalidCredentialsError

    svc = cast("AuthService", auth_service)
    with pytest.raises(InvalidCredentialsError):
        await svc.login("nobody@example.com", "whatever1")


async def test_refresh_rotates_token(auth_service: object) -> None:
    svc = cast("AuthService", auth_service)
    await svc.register("rot@example.com", "password1")
    pair1 = await svc.login("rot@example.com", "password1")

    pair2 = await svc.refresh(pair1.refresh_token)
    assert pair2.refresh_token != pair1.refresh_token
    assert pair2.access_token != pair1.access_token


async def test_refresh_reuse_triggers_mass_revoke(auth_service: object) -> None:
    from core.auth.errors import TokenReuseError

    svc = cast("AuthService", auth_service)
    await svc.register("reuse@example.com", "password1")
    pair1 = await svc.login("reuse@example.com", "password1")

    # First rotation succeeds…
    pair2 = await svc.refresh(pair1.refresh_token)
    # …second use of the ORIGINAL refresh is detected as replay.
    with pytest.raises(TokenReuseError):
        await svc.refresh(pair1.refresh_token)
    # The rotated refresh token is also now revoked.
    with pytest.raises(TokenReuseError):
        await svc.refresh(pair2.refresh_token)


async def test_logout_revokes_refresh(auth_service: object) -> None:
    from core.auth.errors import TokenReuseError

    svc = cast("AuthService", auth_service)
    await svc.register("out@example.com", "password1")
    pair = await svc.login("out@example.com", "password1")

    await svc.logout(pair.refresh_token)
    with pytest.raises(TokenReuseError):
        await svc.refresh(pair.refresh_token)


async def test_get_user_by_access_returns_user(auth_service: object) -> None:
    svc = cast("AuthService", auth_service)
    await svc.register("who@example.com", "password1")
    pair = await svc.login("who@example.com", "password1")

    user = await svc.get_user_by_access(pair.access_token)
    assert user.email == "who@example.com"
