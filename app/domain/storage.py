"""Document blob storage (T-022, DM-002).

A small pluggable interface so the ingest path is agnostic to where bytes live.
MVP ships a local-filesystem backend; an S3 backend can be added later by
implementing the same protocol and selecting it via ``OCR_STORAGE_BACKEND``.

Keys are tenant-prefixed (``<tenant_id>/<document_id>``) so a misconfigured key
can never collide across tenants, and so a tenant's blobs can be enumerated/purged
by prefix during GDPR erasure / retention.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol
from uuid import UUID

from app.config import get_settings


class FileStorage(Protocol):
    async def save(self, tenant_id: UUID | str, document_id: UUID | str, content: bytes) -> str:
        """Persist ``content`` and return its storage key."""
        ...

    async def load(self, storage_key: str) -> bytes: ...

    async def delete(self, storage_key: str) -> None: ...


class LocalFileStorage:
    """Filesystem-backed storage rooted at ``OCR_STORAGE_LOCAL_PATH``."""

    def __init__(self, root: str | None = None) -> None:
        self._root = Path(root or get_settings().storage_local_path)

    @staticmethod
    def _key(tenant_id: UUID | str, document_id: UUID | str) -> str:
        return f"{tenant_id}/{document_id}"

    def _path(self, storage_key: str) -> Path:
        # Guard against traversal: a key is always "<uuid>/<uuid>".
        parts = storage_key.split("/")
        if len(parts) != 2 or any(p in ("", ".", "..") for p in parts):
            raise ValueError(f"invalid storage key: {storage_key!r}")
        return self._root / parts[0] / parts[1]

    async def save(self, tenant_id: UUID | str, document_id: UUID | str, content: bytes) -> str:
        key = self._key(tenant_id, document_id)
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)
        return key

    async def load(self, storage_key: str) -> bytes:
        return await asyncio.to_thread(self._path(storage_key).read_bytes)

    async def delete(self, storage_key: str) -> None:
        await asyncio.to_thread(self._path(storage_key).unlink, True)


_storage: FileStorage | None = None


def get_storage() -> FileStorage:
    global _storage
    if _storage is None:
        backend = get_settings().storage_backend
        if backend == "local":
            _storage = LocalFileStorage()
        else:
            raise ValueError(f"unsupported storage backend: {backend}")
    return _storage
