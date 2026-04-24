"""File-backed conversation memory.

Each session is stored as a single JSON file under :pyattr:`ChatMemory.root`.
The public API is async so call sites in :class:`core.chat_service.ChatService`
stay uniform; blocking ``json.dump`` calls are moved to worker threads via
``asyncio.to_thread``.

# TODO: will be replaced by DB persistence in change
# ``setup-db-postgres-pgvector-alembic``.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.llm.client import ChatMessage

__all__ = ["ChatMemory"]


def _atomic_write(path: Path, payload: bytes) -> None:
    """Write ``payload`` to ``path`` atomically via a sibling ``.tmp`` file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)


class ChatMemory:
    """Minimal async chat-memory backed by one JSON file per session."""

    def __init__(self, root: str | os.PathLike[str] = "./conversations") -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------
    @classmethod
    def from_settings(cls, s: Any | None = None) -> ChatMemory:
        # settings has no dedicated field yet; keep default path.
        del s  # unused — reserved for future MEMORY_DIR setting
        return cls()

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------
    @property
    def root(self) -> Path:
        return self._root

    def _path(self, session_id: str) -> Path:
        if not session_id or "/" in session_id or session_id.startswith("."):
            raise ValueError(f"invalid session id: {session_id!r}")
        return self._root / f"{session_id}.json"

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------
    async def new_session(self) -> str:
        """Mint a random session id and create an empty file for it."""
        session_id = secrets.token_hex(8)

        def _create() -> None:
            _atomic_write(self._path(session_id), b"[]")

        await asyncio.to_thread(_create)
        return session_id

    async def list_sessions(self) -> list[str]:
        def _scan() -> list[str]:
            return sorted(p.stem for p in self._root.glob("*.json"))

        return await asyncio.to_thread(_scan)

    async def get(self, session_id: str) -> list[ChatMessage]:
        path = self._path(session_id)

        def _read() -> list[ChatMessage]:
            if not path.exists():
                return []
            raw = json.loads(path.read_text(encoding="utf-8"))
            return [ChatMessage(role=item["role"], content=item["content"]) for item in raw]

        return await asyncio.to_thread(_read)

    async def append(self, session_id: str, msg: ChatMessage) -> None:
        path = self._path(session_id)

        def _mutate() -> None:
            existing: list[dict[str, str]] = []
            if path.exists():
                existing = json.loads(path.read_text(encoding="utf-8"))
            existing.append(asdict(msg))
            _atomic_write(
                path,
                json.dumps(existing, ensure_ascii=False).encode("utf-8"),
            )

        await asyncio.to_thread(_mutate)

    async def delete_session(self, session_id: str) -> None:
        path = self._path(session_id)

        def _unlink() -> None:
            if path.exists():
                path.unlink()

        await asyncio.to_thread(_unlink)
