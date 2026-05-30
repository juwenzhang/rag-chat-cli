"""Local filesystem object storage for development."""

from __future__ import annotations

import asyncio
from pathlib import Path

from service.storage.base import StoredObject

__all__ = ["LocalObjectStorage"]


class LocalObjectStorage:
    def __init__(self, *, root: str | Path, public_base_url: str = "/uploads") -> None:
        self._root = Path(root)
        self._public_base_url = public_base_url.rstrip("/") or "/uploads"

    async def put_bytes(self, *, key: str, data: bytes, content_type: str) -> StoredObject:
        del content_type
        path = self._path_for_key(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
        return StoredObject(key=key, url=await self.presigned_get_url(key))

    async def presigned_get_url(self, key: str, *, expires_in: int = 3600) -> str:
        del expires_in
        return f"{self._public_base_url}/{key.lstrip('/')}"

    async def delete(self, key: str) -> None:
        path = self._path_for_key(key)
        if path.exists():
            await asyncio.to_thread(path.unlink)

    def _path_for_key(self, key: str) -> Path:
        root = self._root.resolve()
        path = (root / key).resolve()
        path.relative_to(root)
        return path
