"""Qdrant service guard tests (T-039) -- the cross-tenant leakage defenses."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.services.qdrant import (
    CrossTenantLeakageError,
    QdrantService,
    TenantFilterMissingError,
)


class _FakePoint:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload


class _FakeResponse:
    def __init__(self, points: list[_FakePoint]) -> None:
        self.points = points


class _FakeClient:
    def __init__(self, points: list[_FakePoint] | None = None) -> None:
        self._points = points or []
        self.upserted: dict[str, Any] | None = None

    async def query_points(self, **_: Any) -> _FakeResponse:
        return _FakeResponse(self._points)

    async def upsert(self, **kwargs: Any) -> None:
        self.upserted = kwargs


async def test_search_without_tenant_raises() -> None:
    svc = QdrantService(client=_FakeClient(), collection="c")
    with pytest.raises(TenantFilterMissingError):
        await svc.search(tenant_id="", schema_id=uuid.uuid4(), vector=[0.1, 0.2])


async def test_search_returns_matching_tenant_payloads() -> None:
    tid = uuid.uuid4()
    points = [_FakePoint({"tenant_id": str(tid), "expected_json": {"x": 1}})]
    svc = QdrantService(client=_FakeClient(points), collection="c")
    out = await svc.search(tenant_id=tid, schema_id=uuid.uuid4(), vector=[0.1])
    assert out == [{"tenant_id": str(tid), "expected_json": {"x": 1}}]


async def test_search_rejects_cross_tenant_point() -> None:
    """Post-query assertion: a leaked point from another tenant raises."""
    other = str(uuid.uuid4())
    points = [_FakePoint({"tenant_id": other, "expected_json": {}})]
    svc = QdrantService(client=_FakeClient(points), collection="c")
    with pytest.raises(CrossTenantLeakageError):
        await svc.search(tenant_id=uuid.uuid4(), schema_id=uuid.uuid4(), vector=[0.1])


async def test_upsert_stamps_tenant_scoped_payload() -> None:
    client = _FakeClient()
    svc = QdrantService(client=client, collection="c")
    tid, sid, did = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await svc.upsert_example(
        tenant_id=tid, schema_id=sid, document_id=did, vector=[0.1], payload={"input_text": "x"}
    )
    assert client.upserted is not None
    point = client.upserted["points"][0]
    assert point.payload["tenant_id"] == str(tid)
    assert point.payload["schema_id"] == str(sid)
    assert point.payload["document_id"] == str(did)
