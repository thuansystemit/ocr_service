"""DLQ API integration tests (T-060/061)."""

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


async def _seed_dlq(failure_status: str = "pending") -> tuple[uuid.UUID, str, str]:
    tenant_id = uuid.uuid4()
    raw, prefix, key_hash = generate_api_key()
    async with tenant_session(tenant_id) as s:
        await s.execute(
            text(
                "INSERT INTO tenants (id, name, slug, webhook_secret) "
                "VALUES (:id, 'T', :slug, 'sek')"
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
                    "VALUES (:t, :s, 1, 'rejected') RETURNING id"
                ),
                {"t": tenant_id, "s": schema_id},
            )
        ).scalar_one()
        dlq_id = (
            await s.execute(
                text(
                    "INSERT INTO dlq (document_id, tenant_id, failure_reason, status) "
                    "VALUES (:d, :t, 'EXTRACTION_FAILED', :st) RETURNING id"
                ),
                {"d": doc_id, "t": tenant_id, "st": failure_status},
            )
        ).scalar_one()
    return tenant_id, raw, str(dlq_id)


async def _cleanup(tenant_id: uuid.UUID) -> None:
    auth._key_cache.clear()
    async with tenant_session(tenant_id) as s:
        await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_list_and_get_dlq() -> None:
    tenant_id, key, dlq_id = await _seed_dlq()
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with _client() as c:
            listed = await c.get("/api/v1/dlq", headers=headers)
            assert listed.status_code == 200
            assert any(e["id"] == dlq_id for e in listed.json())

            got = await c.get(f"/api/v1/dlq/{dlq_id}", headers=headers)
            assert got.status_code == 200
            assert got.json()["failure_reason"] == "EXTRACTION_FAILED"

            filtered = await c.get("/api/v1/dlq?status=resolved", headers=headers)
            assert filtered.json() == []  # none resolved
    finally:
        await _cleanup(tenant_id)


async def test_retry_non_pending_is_409() -> None:
    tenant_id, key, dlq_id = await _seed_dlq(failure_status="retrying")
    try:
        async with _client() as c:
            resp = await c.post(
                f"/api/v1/dlq/{dlq_id}/retry", headers={"Authorization": f"Bearer {key}"}
            )
        assert resp.status_code == 409
    finally:
        await _cleanup(tenant_id)


async def test_retry_missing_is_404() -> None:
    tenant_id, key, _ = await _seed_dlq()
    try:
        async with _client() as c:
            resp = await c.post(
                f"/api/v1/dlq/{uuid.uuid4()}/retry", headers={"Authorization": f"Bearer {key}"}
            )
        assert resp.status_code == 404
    finally:
        await _cleanup(tenant_id)


async def test_retry_pending_transitions_to_retrying() -> None:
    tenant_id, key, dlq_id = await _seed_dlq(failure_status="pending")
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with _client() as c:
            first = await c.post(f"/api/v1/dlq/{dlq_id}/retry", headers=headers)
            assert first.status_code == 202
            # Idempotency: the same entry is now 'retrying' -> 409.
            second = await c.post(f"/api/v1/dlq/{dlq_id}/retry", headers=headers)
            assert second.status_code == 409
    finally:
        await _cleanup(tenant_id)
