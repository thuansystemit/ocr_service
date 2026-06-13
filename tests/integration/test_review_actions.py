"""Review action + optimistic-locking tests (T-065/066)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import tenant_session
from app.domain.embeddings import set_embedder
from app.main import create_app
from app.services import auth
from app.services.auth import generate_api_key
from app.services.qdrant import set_qdrant_service
from tests.fakes import FakeEmbedder, FakeQdrant

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("db_available")]


@pytest.fixture(autouse=True)
def _fake_rag() -> None:
    set_embedder(FakeEmbedder())  # type: ignore[arg-type]
    set_qdrant_service(FakeQdrant())  # type: ignore[arg-type]
    yield
    set_embedder(None)
    set_qdrant_service(None)


async def _seed_review() -> tuple[uuid.UUID, str, str]:
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
                    "VALUES (:t,:s,1,'review') RETURNING id"
                ),
                {"t": tenant_id, "s": schema_id},
            )
        ).scalar_one()
        result_id = (
            await s.execute(
                text(
                    "INSERT INTO extraction_results (document_id,tenant_id,extracted_json) "
                    'VALUES (:d,:t,\'{"total": "10.00"}\'::jsonb) RETURNING id'
                ),
                {"d": doc_id, "t": tenant_id},
            )
        ).scalar_one()
        review_id = (
            await s.execute(
                text(
                    "INSERT INTO review_tasks (document_id,tenant_id,extraction_result_id,status) "
                    "VALUES (:d,:t,:r,'pending') RETURNING id"
                ),
                {"d": doc_id, "t": tenant_id, "r": result_id},
            )
        ).scalar_one()
    return tenant_id, raw, str(review_id)


async def _cleanup(tenant_id: uuid.UUID) -> None:
    auth._key_cache.clear()
    async with tenant_session(tenant_id) as s:
        await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_accept_marks_completed() -> None:
    tenant_id, key, review_id = await _seed_review()
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with _client() as c:
            resp = await c.post(
                f"/api/v1/review/{review_id}",
                headers=headers,
                json={"action": "accept", "version": 1},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "accepted"
    finally:
        await _cleanup(tenant_id)


async def test_stale_version_is_409() -> None:
    tenant_id, key, review_id = await _seed_review()
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with _client() as c:
            resp = await c.post(
                f"/api/v1/review/{review_id}",
                headers=headers,
                json={"action": "accept", "version": 99},
            )
            assert resp.status_code == 409
    finally:
        await _cleanup(tenant_id)


async def test_correct_updates_extraction() -> None:
    tenant_id, key, review_id = await _seed_review()
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with _client() as c:
            resp = await c.post(
                f"/api/v1/review/{review_id}",
                headers=headers,
                json={
                    "action": "correct",
                    "version": 1,
                    "corrections": {"total": {"old": "10.00", "new": "12.50"}},
                },
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == "corrected"

            detail = await c.get(f"/api/v1/review/{review_id}", headers=headers)
            assert detail.json()["extraction"]["extracted_json"]["total"] == "12.50"
    finally:
        await _cleanup(tenant_id)
