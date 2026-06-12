"""End-to-end auth + tenant-context + RLS through the API (T-014, T-020).

Exercises the real chain: ``Authorization: Bearer ocr_...`` -> SHA-256 hash ->
``auth_resolve_api_key`` SECURITY DEFINER lookup (cross-tenant, RLS-bypassing but
narrow) -> tenant ContextVar -> tenant-scoped session -> RLS-filtered query.

Requires live Postgres with migrations 001-004 applied.
"""

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


async def _seed_tenant(*, with_schema: bool) -> tuple[uuid.UUID, str]:
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
            text("INSERT INTO api_keys (tenant_id, key_hash, key_prefix) " "VALUES (:t, :h, :p)"),
            {"t": tenant_id, "h": key_hash, "p": prefix},
        )
        if with_schema:
            await s.execute(
                text(
                    "INSERT INTO schemas (tenant_id, name, json_schema) "
                    "VALUES (:t, 'invoice', '{}'::jsonb)"
                ),
                {"t": tenant_id},
            )
    return tenant_id, raw


async def _cleanup(*tenant_ids: uuid.UUID) -> None:
    auth._key_cache.clear()
    for tid in tenant_ids:
        async with tenant_session(tid) as s:
            await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tid})


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_missing_auth_is_401() -> None:
    async with _client() as c:
        resp = await c.get("/api/v1/me")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


async def test_bad_api_key_is_401() -> None:
    async with _client() as c:
        resp = await c.get("/api/v1/me", headers={"Authorization": "Bearer ocr_nope"})
    assert resp.status_code == 401


async def test_valid_api_key_resolves_tenant() -> None:
    tenant_id, raw = await _seed_tenant(with_schema=False)
    try:
        async with _client() as c:
            resp = await c.get("/api/v1/me", headers={"Authorization": f"Bearer {raw}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == str(tenant_id)
        assert body["principal"].startswith("apikey:")
        assert set(body["scopes"]) == {"extract", "read"}
    finally:
        await _cleanup(tenant_id)


async def test_rls_scopes_query_to_caller_tenant() -> None:
    """Tenant A has 1 schema, tenant B has 1 schema. A's key must count only 1."""
    tenant_a, key_a = await _seed_tenant(with_schema=True)
    tenant_b, _key_b = await _seed_tenant(with_schema=True)
    try:
        async with _client() as c:
            resp = await c.get(
                "/api/v1/me/schemas/count",
                headers={"Authorization": f"Bearer {key_a}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == str(tenant_a)
        assert body["schema_count"] == 1  # not 2 -> tenant B's schema is invisible
    finally:
        await _cleanup(tenant_a, tenant_b)
