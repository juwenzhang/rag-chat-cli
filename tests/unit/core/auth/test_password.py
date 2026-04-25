"""Unit tests for core.auth.password."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lower bcrypt rounds so the whole file runs in < 1s.

    The cryptographic strength has dedicated tests; everywhere else we only
    need functional correctness.
    """
    # Reset the cached CryptContext so the monkeypatched rounds take effect.
    from core.auth import password as _pw

    _pw._context.cache_clear()

    # Patch the AuthSettings field via the settings singleton's validated model.
    from settings import settings

    monkeypatch.setattr(settings.auth, "bcrypt_rounds", 4, raising=True)


def test_hash_then_verify_roundtrip() -> None:
    from core.auth.password import hash_password, verify_password

    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed) is True


def test_wrong_password_returns_false() -> None:
    from core.auth.password import hash_password, verify_password

    hashed = hash_password("hunter2")
    assert verify_password("hunter3", hashed) is False


def test_malformed_hash_returns_false() -> None:
    from core.auth.password import verify_password

    # A non-bcrypt string must not crash the caller.
    assert verify_password("whatever", "not-a-bcrypt-hash") is False
