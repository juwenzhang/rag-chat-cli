"""Object storage abstraction for user-uploaded files."""

from __future__ import annotations

from service.storage.base import ObjectStorage, StoredObject
from service.storage.factory import build_object_storage
from service.storage.local import LocalObjectStorage
from service.storage.s3 import S3ObjectStorage

__all__ = [
    "LocalObjectStorage",
    "ObjectStorage",
    "S3ObjectStorage",
    "StoredObject",
    "build_object_storage",
]
