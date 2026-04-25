"""Unit tests for core.auth.tokens — encode / decode / error paths."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest


def test_access_token_roundtrip() -> None:
    from core.auth.tokens import create_access_token, decode_token

    uid = uuid.uuid4()
    token = create_access_token(uid)
    payload = decode_token(token, expected_type="access")
    assert payload.sub == str(uid)
    assert payload.type == "access"
    assert payload.exp > payload.iat


def test_refresh_token_roundtrip_returns_jti() -> None:
    from core.auth.tokens import create_refresh_token, decode_token

    uid = uuid.uuid4()
    token, jti = create_refresh_token(uid)
    payload = decode_token(token, expected_type="refresh")
    assert payload.jti == jti
    assert payload.type == "refresh"


def test_wrong_expected_type_raises_invalid() -> None:
    from core.auth.errors import TokenInvalidError
    from core.auth.tokens import create_access_token, decode_token

    token = create_access_token(uuid.uuid4())
    with pytest.raises(TokenInvalidError):
        decode_token(token, expected_type="refresh")


def test_tampered_signature_raises_invalid() -> None:
    from core.auth.errors import TokenInvalidError
    from core.auth.tokens import create_access_token, decode_token

    token = create_access_token(uuid.uuid4())
    # Strip the final signature segment entirely — guaranteed to fail
    # signature verification regardless of base64url quirks.
    header, payload, _sig = token.split(".")
    tampered = f"{header}.{payload}.AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    with pytest.raises(TokenInvalidError):
        decode_token(tampered, expected_type="access")


def test_tampered_payload_raises_invalid() -> None:
    """Flipping a byte in the payload must invalidate the signature."""
    from core.auth.errors import TokenInvalidError
    from core.auth.tokens import create_access_token, decode_token

    token = create_access_token(uuid.uuid4())
    header, payload, sig = token.split(".")
    # Mutate the payload — any change breaks HMAC.
    mutated_payload = payload[:-2] + ("Aa" if payload[-2:] != "Aa" else "Bb")
    tampered = f"{header}.{mutated_payload}.{sig}"
    with pytest.raises(TokenInvalidError):
        decode_token(tampered, expected_type="access")


def test_expired_token_raises_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.auth import tokens as tok
    from core.auth.errors import TokenExpiredError

    # Freeze "now" to one hour in the past so exp has already elapsed.
    past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    monkeypatch.setattr(tok, "_now", lambda: past)
    token = tok.create_access_token(uuid.uuid4(), ttl_min=1)

    with pytest.raises(TokenExpiredError):
        tok.decode_token(token, expected_type="access")
