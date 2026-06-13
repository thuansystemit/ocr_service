"""Audit export API tests (T-072/074)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import tenant_session
from app.main import create_app
from app.services import audit, auth
from app.services.auth import generate_api_key

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("db_available")]


async def _seed_with_events(n: int) -> tuple[uuid.UUID, str]:
    tenant_id = uuid.uuid4()
    raw, prefix, key_hash = generate_api_key()
    async with tenant_session(tenant_id) as s:
        await s.execute(
            text("INSERT INTO tenants (id,name,slug,webhook_secret) VALUES (:id,'T',:slug,'sek')"),
            {"id": tenant_id, "slug": f"t-{tenant_id.hex[:10]}"},
        )
        await s.execute(
            text("INSERT INTO api_keys (tenant_id,key_hash,key_prefix) VALUES (:t,:h,:p)"),
            {"t": tenant_id, "h": key_hash, "p": prefix},
        )
    async with tenant_session(tenant_id) as s:
        for i in range(n):
            await audit.append_event(
                s,
                tenant_id=tenant_id,
                event_type="PIPELINE_COMPLETED",
                actor="system:test",
                status="completed",
                payload={"i": i},
            )
    return tenant_id, raw


async def _cleanup(tenant_id: uuid.UUID) -> None:
    auth._key_cache.clear()
    async with tenant_session(tenant_id) as s:
        await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_export_ndjson() -> None:
    tenant_id, key = await _seed_with_events(5)
    try:
        async with _client() as c:
            resp = await c.get("/api/v1/audit/export", headers={"Authorization": f"Bearer {key}"})
        assert resp.status_code == 200
        lines = [ln for ln in resp.text.splitlines() if ln.strip()]
        assert len(lines) == 5
        assert all("PIPELINE_COMPLETED" in ln for ln in lines)
    finally:
        await _cleanup(tenant_id)


async def test_export_csv_has_header() -> None:
    tenant_id, key = await _seed_with_events(2)
    try:
        async with _client() as c:
            resp = await c.get(
                "/api/v1/audit/export?format=csv", headers={"Authorization": f"Bearer {key}"}
            )
        assert resp.status_code == 200
        rows = [ln for ln in resp.text.splitlines() if ln.strip()]
        assert rows[0].startswith("id,document_id,event_type")
        assert len(rows) == 3  # header + 2 events
    finally:
        await _cleanup(tenant_id)


async def test_export_is_tenant_scoped() -> None:
    tenant_a, _key_a = await _seed_with_events(3)
    tenant_b, key_b = await _seed_with_events(1)
    try:
        async with _client() as c:
            resp = await c.get("/api/v1/audit/export", headers={"Authorization": f"Bearer {key_b}"})
        lines = [ln for ln in resp.text.splitlines() if ln.strip()]
        assert len(lines) == 1  # only tenant B's event
    finally:
        await _cleanup(tenant_a)
        await _cleanup(tenant_b)
