"""Review queue API integration tests (T-064)."""

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


async def _seed_review() -> tuple[uuid.UUID, str, str]:
    """Seed a tenant with one MEDIUM document + extraction + review task."""
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
        schema_id = (
            await s.execute(
                text(
                    "INSERT INTO schemas (tenant_id, name, json_schema) "
                    "VALUES (:t, 'invoice', '{}'::jsonb) RETURNING id"
                ),
                {"t": tenant_id},
            )
        ).scalar_one()
        doc_id = (
            await s.execute(
                text(
                    "INSERT INTO documents (tenant_id, schema_id, schema_version, status) "
                    "VALUES (:t, :s, 1, 'review') RETURNING id"
                ),
                {"t": tenant_id, "s": schema_id},
            )
        ).scalar_one()
        result_id = (
            await s.execute(
                text(
                    "INSERT INTO extraction_results (document_id, tenant_id, extracted_json) "
                    'VALUES (:d, :t, \'{"total": "50.00"}\'::jsonb) RETURNING id'
                ),
                {"d": doc_id, "t": tenant_id},
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO review_tasks (document_id, tenant_id, extraction_result_id, status) "
                "VALUES (:d, :t, :r, 'pending')"
            ),
            {"d": doc_id, "t": tenant_id, "r": result_id},
        )
    return tenant_id, raw, str(doc_id)


async def _cleanup(tenant_id: uuid.UUID) -> None:
    auth._key_cache.clear()
    async with tenant_session(tenant_id) as s:
        await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_review_queue_lists_open_items() -> None:
    tenant_id, key, doc_id = await _seed_review()
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with _client() as c:
            listed = await c.get("/api/v1/review", headers=headers)
            assert listed.status_code == 200
            items = listed.json()
            assert len(items) == 1
            review_id = items[0]["id"]
            assert items[0]["document_id"] == doc_id

            detail = await c.get(f"/api/v1/review/{review_id}", headers=headers)
            assert detail.status_code == 200
            body = detail.json()
            assert body["document_id"] == doc_id
            assert body["extraction"]["extracted_json"] == {"total": "50.00"}
    finally:
        await _cleanup(tenant_id)


async def test_review_queue_is_tenant_isolated() -> None:
    tenant_a, _key_a, _ = await _seed_review()
    tenant_b, key_b, _ = await _seed_review()
    try:
        async with _client() as c:
            # Tenant B sees only its own review item, not tenant A's.
            listed = await c.get("/api/v1/review", headers={"Authorization": f"Bearer {key_b}"})
            assert listed.status_code == 200
            assert len(listed.json()) == 1
    finally:
        await _cleanup(tenant_a)
        await _cleanup(tenant_b)
