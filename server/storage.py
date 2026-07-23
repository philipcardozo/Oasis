"""Private object storage abstraction for exports and large user artifacts.

Local filesystem backend for dev; S3-compatible for staging/production. Objects
are private by default; downloads are authorized by the app, never by bucket
path. Never exposes a raw storage path as authorization.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from server.config import Settings, get_settings


@dataclass
class StoredObject:
    key: str
    size: int
    checksum: str
    content_type: str
    created_at: float
    owner_id: str | None


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        # Reject traversal outright rather than silently rewriting the key.
        if ".." in key.split("/") or key.startswith("/") or "\\" in key:
            raise ValueError("invalid storage key")
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str, owner_id: str | None = None) -> StoredObject:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return StoredObject(key=key, size=len(data), checksum=hashlib.sha256(data).hexdigest(),
                            content_type=content_type, created_at=time.time(), owner_id=owner_id)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()


class S3Storage:  # pragma: no cover - exercised only against a real/mock S3
    def __init__(self, bucket: str, region: str, endpoint_url: str | None):
        import boto3

        self.bucket = bucket
        self._s3 = boto3.client("s3", region_name=region or None, endpoint_url=endpoint_url or None)

    def put(self, key: str, data: bytes, content_type: str, owner_id: str | None = None) -> StoredObject:
        self._s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                            Metadata={"owner": owner_id or ""}, ACL="private")
        return StoredObject(key=key, size=len(data), checksum=hashlib.sha256(data).hexdigest(),
                            content_type=content_type, created_at=time.time(), owner_id=owner_id)

    def get(self, key: str) -> bytes:
        return self._s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        self._s3.delete_object(Bucket=self.bucket, Key=key)


def get_storage(settings: Settings | None = None):
    settings = settings or get_settings()
    if settings.storage_backend == "s3":
        return S3Storage(settings.s3_bucket, settings.s3_region, settings.s3_endpoint_url or None)
    return LocalStorage(settings.storage_local_dir)
