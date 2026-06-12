from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "UploadSession",
    "UploadSessionStore",
]

_META_FILENAME = "meta.json"
_CHUNKS_DIRNAME = "chunks"
_SESSION_ID_RE = re.compile(r"^[a-f0-9-]{36}$")


@dataclass(frozen=True, slots=True)
class UploadSession:
    upload_id: str
    user_id: uuid.UUID
    filename: str
    content_type: str
    total_size: int
    chunk_size: int
    source_hash: str | None
    created_at: float
    root: Path

    @property
    def chunks_dir(self) -> Path:
        return self.root / _CHUNKS_DIRNAME

    @property
    def expected_chunks(self) -> int:
        if self.total_size <= 0:
            return 0
        return (self.total_size + self.chunk_size - 1) // self.chunk_size


class UploadSessionStore:
    """Filesystem-backed temporary storage for in-flight chunked uploads."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        filename: str,
        content_type: str,
        total_size: int,
        chunk_size: int,
        source_hash: str | None,
    ) -> UploadSession:
        upload_id = str(uuid.uuid4())
        session_root = self._session_root(user_id, upload_id)
        meta = {
            "upload_id": upload_id,
            "user_id": str(user_id),
            "filename": filename,
            "content_type": content_type,
            "total_size": int(total_size),
            "chunk_size": int(chunk_size),
            "source_hash": source_hash,
            "created_at": time.time(),
        }
        await asyncio.to_thread(self._write_meta_sync, session_root, meta)
        return self._session_from_meta(meta, session_root)

    async def get(self, *, user_id: uuid.UUID, upload_id: str) -> UploadSession:
        if not _SESSION_ID_RE.match(upload_id):
            raise FileNotFoundError(upload_id)
        session_root = self._session_root(user_id, upload_id)
        meta = await asyncio.to_thread(self._read_meta_sync, session_root)
        if str(meta.get("user_id")) != str(user_id):
            raise FileNotFoundError(upload_id)
        return self._session_from_meta(meta, session_root)

    async def write_chunk(
        self,
        session: UploadSession,
        *,
        index: int,
        data: bytes,
    ) -> None:
        if index < 0 or index >= session.expected_chunks:
            raise ValueError(f"chunk index out of range: {index}")
        # All chunks except the last must be exactly chunk_size; the last may be smaller.
        is_last = index == session.expected_chunks - 1
        expected_size = (
            session.total_size - session.chunk_size * (session.expected_chunks - 1)
            if is_last
            else session.chunk_size
        )
        if len(data) != expected_size:
            raise ValueError(
                f"chunk {index} has wrong size: got {len(data)}, expected {expected_size}"
            )
        await asyncio.to_thread(self._write_chunk_sync, session, index, data)

    async def received_indices(self, session: UploadSession) -> list[int]:
        return await asyncio.to_thread(self._received_indices_sync, session)

    async def assemble(self, session: UploadSession) -> bytes:
        return await asyncio.to_thread(self._assemble_sync, session)

    async def discard(self, session: UploadSession) -> None:
        await asyncio.to_thread(self._discard_sync, session)

    async def cleanup_expired(self, *, max_age_seconds: float) -> int:
        return await asyncio.to_thread(self._cleanup_expired_sync, max_age_seconds)

    def _session_root(self, user_id: uuid.UUID, upload_id: str) -> Path:
        return self._root / str(user_id) / upload_id

    def _session_from_meta(self, meta: dict[str, Any], session_root: Path) -> UploadSession:
        return UploadSession(
            upload_id=str(meta["upload_id"]),
            user_id=uuid.UUID(str(meta["user_id"])),
            filename=str(meta["filename"]),
            content_type=str(meta["content_type"]),
            total_size=int(meta["total_size"]),
            chunk_size=int(meta["chunk_size"]),
            source_hash=meta.get("source_hash"),
            created_at=float(meta["created_at"]),
            root=session_root,
        )

    @staticmethod
    def _write_meta_sync(session_root: Path, meta: dict[str, Any]) -> None:
        chunks_dir = session_root / _CHUNKS_DIRNAME
        chunks_dir.mkdir(parents=True, exist_ok=True)
        meta_path = session_root / _META_FILENAME
        meta_path.write_text(json.dumps(meta), encoding="utf-8")

    @staticmethod
    def _read_meta_sync(session_root: Path) -> dict[str, Any]:
        meta_path = session_root / _META_FILENAME
        if not meta_path.is_file():
            raise FileNotFoundError(str(session_root))
        data: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        return data

    @staticmethod
    def _write_chunk_sync(session: UploadSession, index: int, data: bytes) -> None:
        chunks_dir = session.chunks_dir
        chunks_dir.mkdir(parents=True, exist_ok=True)
        target = chunks_dir / f"{index}"
        tmp = chunks_dir / f"{index}.partial"
        tmp.write_bytes(data)
        tmp.replace(target)  # atomic on POSIX/NTFS

    @staticmethod
    def _received_indices_sync(session: UploadSession) -> list[int]:
        if not session.chunks_dir.is_dir():
            return []
        indices: list[int] = []
        for entry in session.chunks_dir.iterdir():
            if not entry.is_file() or entry.suffix == ".partial":
                continue
            try:
                indices.append(int(entry.name))
            except ValueError:
                continue
        indices.sort()
        return indices

    @staticmethod
    def _assemble_sync(session: UploadSession) -> bytes:
        # Pre-size the buffer so we don't pay for repeated reallocations on
        # the (relatively small, ≤8MB) image upload path.
        buf = bytearray(session.total_size)
        cursor = 0
        for index in range(session.expected_chunks):
            chunk_path = session.chunks_dir / f"{index}"
            if not chunk_path.is_file():
                raise FileNotFoundError(f"missing chunk {index}")
            data = chunk_path.read_bytes()
            buf[cursor : cursor + len(data)] = data
            cursor += len(data)
        if cursor != session.total_size:
            raise ValueError(
                f"assembled size mismatch: got {cursor}, expected {session.total_size}"
            )
        return bytes(buf)

    @staticmethod
    def _discard_sync(session: UploadSession) -> None:
        if session.root.is_dir():
            shutil.rmtree(session.root, ignore_errors=True)
        # Also try to clean up the per-user dir if it's empty now — harmless if not.
        parent = session.root.parent
        try:
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass

    def _cleanup_expired_sync(self, max_age_seconds: float) -> int:
        if not self._root.is_dir():
            return 0
        cutoff = time.time() - max_age_seconds
        removed = 0
        for user_dir in self._root.iterdir():
            if not user_dir.is_dir():
                continue
            for session_dir in user_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                meta_path = session_dir / _META_FILENAME
                created_at = (
                    meta_path.stat().st_mtime
                    if meta_path.is_file()
                    else session_dir.stat().st_mtime
                )
                if created_at < cutoff:
                    shutil.rmtree(session_dir, ignore_errors=True)
                    removed += 1
            try:
                if not any(user_dir.iterdir()):
                    user_dir.rmdir()
            except OSError:
                pass
        return removed
