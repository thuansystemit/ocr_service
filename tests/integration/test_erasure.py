"""GDPR erasure tests (T-075/076)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import tenant_session
from app.main import create_app
from app.services import auth
from app.services.auth import generate_api_key
from app.services.qdrant import set_qdrant_service
from tests.fakes import FakeQdrant

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("db_available")]


@pytest.fixture(autouse=True)
def _fake_qdrant() -> None:
    set_qdrant_service(FakeQdrant())  # type: ignore[arg-type]
    yield
    set_qdrant_service(None)


async def _seed_document() -> tuple[uuid.UUID, str, str]:
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
        schema_id = (
            await s.execute(
                text(
                    "INSERT INTO schemas (tenant_id,name,json_schema) "
                    "VALUES (:t,'invoice','{}'::jsonb) RETURNING id"
                ),
                {"t": tenant_id},
            )
        ).scalar_one()
        doc_id = (
            await s.execute(
                text(
                    "INSERT INTO documents (tenant_id,schema_id,schema_version,status) "
                    "VALUES (:t,:s,1,'completed') RETURNING id"
                ),
                {"t": tenant_id, "s": schema_id},
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO extraction_results (document_id,tenant_id,extracted_json) "
                'VALUES (:d,:t,\'{"total": "9"}\'::jsonb)'
            ),
            {"d": doc_id, "t": tenant_id},
        )
    return tenant_id, raw, str(doc_id)


async def _cleanup(tenant_id: uuid.UUID) -> None:
    auth._key_cache.clear()
    async with tenant_session(tenant_id) as s:
        await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_erasure_deletes_document_and_leaves_tombstone() -> None:
    tenant_id, key, doc_id = await _seed_document()
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with _client() as c:
            resp = await c.delete(f"/api/v1/documents/{doc_id}", headers=headers)
            assert resp.status_code == 202
            assert resp.json()["status"] == "erased"

            # Document (and cascaded extraction) is gone.
            gone = await c.get(f"/api/v1/documents/{doc_id}", headers=headers)
            assert gone.status_code == 404

        async with tenant_session(tenant_id) as s:
            extractions = (
                await s.execute(
                    text("SELECT count(*) FROM extraction_results WHERE document_id = :d"),
                    {"d": doc_id},
                )
            ).scalar_one()
            tombstone = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM audit_log "
                        "WHERE document_id = :d AND event_type = 'ERASURE_COMPLETED'"
                    ),
                    {"d": doc_id},
                )
            ).scalar_one()
        assert extractions == 0  # cascade-deleted
        assert tombstone == 1  # erasure proof remains
    finally:
        await _cleanup(tenant_id)


async def test_erasure_of_missing_document_is_404() -> None:
    tenant_id, key, _ = await _seed_document()
    try:
        async with _client() as c:
            resp = await c.delete(
                f"/api/v1/documents/{uuid.uuid4()}", headers={"Authorization": f"Bearer {key}"}
            )
        assert resp.status_code == 404
    finally:
        await _cleanup(tenant_id)
