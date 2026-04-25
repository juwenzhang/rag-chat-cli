"""Local token store for the CLI (AGENTS.md §6 / add-jwt-auth/design.md).

Stores the access + refresh pair at ``~/.config/rag-chat/token.json`` with
``0600`` permissions on POSIX. Windows silently skips the chmod — there is
no direct equivalent, but an ACL-based hardening is left for a future change.

The file format is exactly :class:`core.auth.service.TokenPair` serialised as
JSON (ISO-8601 timestamps). This keeps parsing trivial and the file
human-inspectable.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from core.auth.service import TokenPair

__all__ = [
    "DEFAULT_TOKEN_PATH",
    "clear",
    "import_from_string",
    "load",
    "save",
    "token_path",
]


def _default_token_path() -> Path:
    return Path("~/.config/rag-chat/token.json").expanduser()


#: Resolved at import time so tests can monkeypatch ``HOME`` before touching
#: this module. Read via :func:`token_path` everywhere else.
DEFAULT_TOKEN_PATH = _default_token_path()


def token_path() -> Path:
    """Return the current token file path.

    Re-evaluated on each call so ``monkeypatch.setenv("HOME", ...)`` inside a
    single test actually takes effect.
    """
    return _default_token_path()


def _serialise(pair: TokenPair) -> str:
    data = asdict(pair)
    data["access_expires_at"] = pair.access_expires_at.isoformat()
    data["refresh_expires_at"] = pair.refresh_expires_at.isoformat()
    return json.dumps(data, indent=2, ensure_ascii=False)


def _deserialise(raw: str) -> TokenPair:
    obj = json.loads(raw)
    return TokenPair(
        access_token=str(obj["access_token"]),
        refresh_token=str(obj["refresh_token"]),
        access_expires_at=datetime.fromisoformat(obj["access_expires_at"]),
        refresh_expires_at=datetime.fromisoformat(obj["refresh_expires_at"]),
        token_type=str(obj.get("token_type", "bearer")),
    )


def save(pair: TokenPair, *, path: Path | None = None) -> Path:
    """Atomically persist ``pair`` and chmod the file to ``0600`` on POSIX.

    Uses the classic ``write-tmp + os.replace`` pattern so a crash mid-write
    never leaves a half-token behind.
    """
    target = path or token_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(_serialise(pair), encoding="utf-8")
    # chmod BEFORE replace so the file is never world-readable in between.
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    return target


def load(*, path: Path | None = None) -> TokenPair | None:
    """Return the stored pair, or ``None`` if the file does not exist."""
    target = path or token_path()
    if not target.exists():
        return None
    return _deserialise(target.read_text(encoding="utf-8"))


def clear(*, path: Path | None = None) -> None:
    """Delete the token file. No-op if it is already gone."""
    target = path or token_path()
    if target.exists():
        target.unlink()


def import_from_string(encoded: str) -> TokenPair:
    """Parse a JSON-encoded :class:`TokenPair` (as produced by the Web UI).

    The full ``rag://token?a=...&r=...`` URL scheme is reserved for the
    ``web-cli-token-handoff`` change; for now we accept the plain JSON body.
    """
    return _deserialise(encoded)
