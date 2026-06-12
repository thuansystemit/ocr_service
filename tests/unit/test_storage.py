"""LocalFileStorage unit tests (T-022)."""

from __future__ import annotations

import uuid

import pytest

from app.domain.storage import LocalFileStorage


async def test_save_load_delete_round_trip(tmp_path) -> None:
    storage = LocalFileStorage(root=str(tmp_path))
    tenant_id, document_id = uuid.uuid4(), uuid.uuid4()

    key = await storage.save(tenant_id, document_id, b"hello bytes")
    assert key == f"{tenant_id}/{document_id}"
    assert await storage.load(key) == b"hello bytes"

    await storage.delete(key)
    with pytest.raises(FileNotFoundError):
        await storage.load(key)


async def test_delete_is_idempotent(tmp_path) -> None:
    storage = LocalFileStorage(root=str(tmp_path))
    await storage.delete(f"{uuid.uuid4()}/{uuid.uuid4()}")  # missing -> no error


@pytest.mark.parametrize("bad_key", ["../etc/passwd", "a", "a/b/c", "../../x", "/abs/path"])
async def test_path_traversal_rejected(tmp_path, bad_key: str) -> None:
    storage = LocalFileStorage(root=str(tmp_path))
    with pytest.raises(ValueError):
        await storage.load(bad_key)
