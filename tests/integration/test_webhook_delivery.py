"""Webhook delivery service integration tests (T-056/057)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import text

from app.db.session import tenant_session
from app.services.webhook_delivery import WebhookDeliverer

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("db_available")]


class _FakeClient:
    def __init__(self, status: int) -> None:
        self._status = status
        self.calls = 0

    async def post(self, url: str, content: Any = None, headers: Any = None) -> SimpleNamespace:
        self.calls += 1
        return SimpleNamespace(status_code=self._status)


async def _seed_document() -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    async with tenant_session(tenant_id) as s:
        await s.execute(
            text(
                "INSERT INTO tenants (id, name, slug, webhook_secret) "
                "VALUES (:id, 'T', :slug, 'sek')"
            ),
            {"id": tenant_id, "slug": f"t-{tenant_id.hex[:10]}"},
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
                    "VALUES (:t, :s, 1, 'completed') RETURNING id"
                ),
                {"t": tenant_id, "s": schema_id},
            )
        ).scalar_one()
    return tenant_id, doc_id


async def _cleanup(tenant_id: uuid.UUID) -> None:
    async with tenant_session(tenant_id) as s:
        await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})


async def test_successful_delivery_records_attempt() -> None:
    tenant_id, doc_id = await _seed_document()
    fake = _FakeClient(status=200)
    try:
        async with tenant_session(tenant_id) as s:
            ok = await WebhookDeliverer(client=fake).deliver(
                s,
                tenant_id=tenant_id,
                document_id=doc_id,
                webhook_url="https://example.test/hook",
                webhook_secret="sek",
                payload={"document_id": str(doc_id), "status": "completed"},
            )
        assert ok is True
        assert fake.calls == 1
        async with tenant_session(tenant_id) as s:
            n = (
                await s.execute(
                    text("SELECT count(*) FROM webhook_deliveries WHERE document_id = :d"),
                    {"d": doc_id},
                )
            ).scalar_one()
        assert n == 1
    finally:
        await _cleanup(tenant_id)


async def test_exhaustion_writes_dlq() -> None:
    tenant_id, doc_id = await _seed_document()
    fake = _FakeClient(status=500)
    try:
        async with tenant_session(tenant_id) as s:
            ok = await WebhookDeliverer(client=fake, schedule=(0, 0, 0)).deliver(
                s,
                tenant_id=tenant_id,
                document_id=doc_id,
                webhook_url="https://example.test/hook",
                webhook_secret="sek",
                payload={"document_id": str(doc_id), "status": "completed"},
            )
        assert ok is False
        assert fake.calls == 3  # all attempts in the schedule
        async with tenant_session(tenant_id) as s:
            attempts = (
                await s.execute(
                    text("SELECT count(*) FROM webhook_deliveries WHERE document_id = :d"),
                    {"d": doc_id},
                )
            ).scalar_one()
            reason = (
                await s.execute(
                    text("SELECT failure_reason FROM dlq WHERE document_id = :d"), {"d": doc_id}
                )
            ).scalar_one()
        assert attempts == 3
        assert reason == "WEBHOOK_DELIVERY_FAILED"
    finally:
        await _cleanup(tenant_id)
