"""Schema seed + activation lifecycle (T-027/028/029)."""

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


async def _seed() -> tuple[uuid.UUID, str]:
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
    return tenant_id, raw


async def _cleanup(tenant_id: uuid.UUID) -> None:
    auth._key_cache.clear()
    async with tenant_session(tenant_id) as s:
        await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


_PAYLOAD = {"name": "invoice", "json_schema": {"type": "object"}, "required_fields": []}


async def test_activation_requires_three_seeds() -> None:
    tenant_id, key = await _seed()
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with _client() as c:
            created = await c.post("/api/v1/schemas", headers=headers, json=_PAYLOAD)
            schema_id = created.json()["id"]
            assert created.json()["status"] == "draft"

            # Too few seeds -> 409.
            early = await c.post(f"/api/v1/schemas/{schema_id}/activate", headers=headers)
            assert early.status_code == 409

            for i in range(3):
                seed = await c.post(
                    f"/api/v1/schemas/{schema_id}/seeds",
                    headers=headers,
                    json={
                        "input_text": f"example {i} invoice text",
                        "expected_json": {"total": "1"},
                    },
                )
                assert seed.status_code == 200
            assert seed.json()["seed_count"] == 3

            activated = await c.post(f"/api/v1/schemas/{schema_id}/activate", headers=headers)
            assert activated.status_code == 200
            assert activated.json()["status"] == "active"

        # A schema_versions row was snapshotted on activation.
        async with tenant_session(tenant_id) as s:
            n = (
                await s.execute(
                    text("SELECT count(*) FROM schema_versions WHERE schema_id = :s"),
                    {"s": schema_id},
                )
            ).scalar_one()
        assert n == 1
    finally:
        await _cleanup(tenant_id)
