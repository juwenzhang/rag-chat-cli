"""Unit tests for app.auth_local (CLI token file)."""

from __future__ import annotations

import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def _sample_pair() -> object:
    from core.auth.service import TokenPair

    now = datetime.now(tz=timezone.utc)
    return TokenPair(
        access_token="a" * 32,
        refresh_token="r" * 32,
        access_expires_at=now + timedelta(minutes=15),
        refresh_expires_at=now + timedelta(days=7),
    )


def test_save_load_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    from app import auth_local

    pair = _sample_pair()
    path = auth_local.save(pair)  # type: ignore[arg-type]
    assert path.exists()
    assert path.parent == tmp_path / ".config" / "rag-chat"

    loaded = auth_local.load()
    assert loaded is not None
    assert loaded.access_token == "a" * 32
    assert loaded.refresh_token == "r" * 32


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions only")
def test_save_writes_0600(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    from app import auth_local

    path = auth_local.save(_sample_pair())  # type: ignore[arg-type]
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_load_returns_none_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    from app import auth_local

    assert auth_local.load() is None


def test_clear_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    from app import auth_local

    auth_local.clear()  # no file yet — must not raise
    auth_local.save(_sample_pair())  # type: ignore[arg-type]
    auth_local.clear()
    assert auth_local.load() is None
