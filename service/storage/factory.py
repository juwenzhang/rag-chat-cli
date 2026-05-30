"""Build object storage from settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from service.storage.base import ObjectStorage
from service.storage.local import LocalObjectStorage
from service.storage.s3 import S3ObjectStorage

if TYPE_CHECKING:
    from settings import Settings

__all__ = ["build_object_storage"]


def build_object_storage(settings: Settings) -> ObjectStorage:
    cfg = settings.storage
    if cfg.backend == "s3":
        assert cfg.s3_endpoint_url is not None
        assert cfg.s3_access_key is not None
        assert cfg.s3_secret_key is not None
        assert cfg.s3_bucket is not None
        return S3ObjectStorage(
            endpoint_url=cfg.s3_endpoint_url,
            public_endpoint_url=cfg.s3_public_endpoint_url or cfg.s3_endpoint_url,
            access_key=cfg.s3_access_key,
            secret_key=cfg.s3_secret_key,
            bucket=cfg.s3_bucket,
            region=cfg.s3_region or "us-east-1",
        )
    return LocalObjectStorage(root=cfg.local_root, public_base_url=cfg.public_base_url)
