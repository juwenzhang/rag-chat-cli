"""Storage protocol shared by local and S3-compatible backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["ObjectStorage", "StoredObject"]


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    url: str


@runtime_checkable
class ObjectStorage(Protocol):
    async def put_bytes(self, *, key: str, data: bytes, content_type: str) -> StoredObject: ...
    async def presigned_get_url(self, key: str, *, expires_in: int = 3600) -> str: ...
    async def delete(self, key: str) -> None: ...
