"""S3-compatible object storage, including MinIO."""

from __future__ import annotations

import asyncio

from service.storage.base import StoredObject

__all__ = ["S3ObjectStorage"]


class S3ObjectStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        public_endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
    ) -> None:
        import boto3
        from botocore.config import Config

        self._bucket = bucket
        self._public_endpoint_url = public_endpoint_url.rstrip("/")
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    async def put_bytes(self, *, key: str, data: bytes, content_type: str) -> StoredObject:
        await asyncio.to_thread(self._ensure_bucket)
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return StoredObject(key=key, url=await self.presigned_get_url(key))

    async def get_bytes(self, key: str) -> bytes:
        obj = await asyncio.to_thread(
            self._client.get_object,
            Bucket=self._bucket,
            Key=key,
        )
        return await asyncio.to_thread(obj["Body"].read)

    async def presigned_get_url(self, key: str, *, expires_in: int = 3600) -> str:
        url = await asyncio.to_thread(
            self._client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        if self._public_endpoint_url:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            internal = f"{parsed.scheme}://{parsed.netloc}"
            url = url.replace(internal, self._public_endpoint_url, 1)
        return str(url)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            self._client.create_bucket(Bucket=self._bucket)
