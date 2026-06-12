"""Schema-registry CRUD + tenant isolation (T-026)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import tenant_session
from app.main import create_app
from app.services import auth
from app.services.auth import generate_api_key

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("db_available")]


async def _seed() -> tuple[uuid.UUID, str]:
    tenant_id = uuid.uuid4()
    raw, prefix, key_hash = generate_api_key()
    async with tenant_session(tenant_id) as s:
        await s.execute(
            text(
                "INSERT INTO tenants (id, name, slug, webhook_secret) "
                "VALUES (:id, 'T', :slug, 'seed-secret')"
            ),
            {"id": tenant_id, "slug": f"t-{tenant_id.hex[:10]}"},
        )
        await s.execute(
            text("INSERT INTO api_keys (tenant_id, key_hash, key_prefix) VALUES (:t, :h, :p)"),
            {"t": tenant_id, "h": key_hash, "p": prefix},
        )
    return tenant_id, raw


async def _cleanup(*tenant_ids: uuid.UUID) -> None:
    auth._key_cache.clear()
    for tid in tenant_ids:
        async with tenant_session(tid) as s:
            await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tid})


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


_PAYLOAD = {
    "name": "invoice",
    "description": "Invoice extraction",
    "json_schema": {"type": "object", "properties": {"total": {"type": "string"}}},
    "required_fields": ["total"],
    "pii_fields": [],
    "confidence_high": 0.85,
    "confidence_medium": 0.60,
}


async def test_schema_crud_round_trip() -> None:
    tenant_id, key = await _seed()
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with _client() as c:
            created = await c.post("/api/v1/schemas", headers=headers, json=_PAYLOAD)
            assert created.status_code == 201, created.text
            schema = created.json()
            assert schema["status"] == "draft"
            schema_id = schema["id"]

            got = await c.get(f"/api/v1/schemas/{schema_id}", headers=headers)
            assert got.status_code == 200
            assert got.json()["name"] == "invoice"

            listed = await c.get("/api/v1/schemas", headers=headers)
            assert listed.status_code == 200
            assert any(s["id"] == schema_id for s in listed.json())

            updated = await c.put(
                f"/api/v1/schemas/{schema_id}",
                headers=headers,
                json={**_PAYLOAD, "description": "updated"},
            )
            assert updated.status_code == 200
            assert updated.json()["description"] == "updated"
    finally:
        await _cleanup(tenant_id)


async def test_duplicate_schema_name_is_409() -> None:
    tenant_id, key = await _seed()
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with _client() as c:
            first = await c.post("/api/v1/schemas", headers=headers, json=_PAYLOAD)
            assert first.status_code == 201
            dup = await c.post("/api/v1/schemas", headers=headers, json=_PAYLOAD)
            assert dup.status_code == 409
    finally:
        await _cleanup(tenant_id)


async def test_schemas_are_tenant_isolated() -> None:
    tenant_a, key_a = await _seed()
    tenant_b, key_b = await _seed()
    try:
        async with _client() as c:
            await c.post(
                "/api/v1/schemas", headers={"Authorization": f"Bearer {key_a}"}, json=_PAYLOAD
            )
            # Tenant B lists schemas -> must not see tenant A's.
            listed_b = await c.get("/api/v1/schemas", headers={"Authorization": f"Bearer {key_b}"})
            assert listed_b.status_code == 200
            assert listed_b.json() == []
    finally:
        await _cleanup(tenant_a, tenant_b)
