"""Audit service integration tests (T-071)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.db.session import tenant_session
from app.services import audit

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("db_available")]


def test_payload_hash_is_stable_and_order_independent() -> None:
    h1 = audit.payload_hash({"a": 1, "b": 2})
    h2 = audit.payload_hash({"b": 2, "a": 1})
    assert h1 == h2 and h1 is not None and len(h1) == 64
    assert audit.payload_hash(None) is None


async def test_append_event_writes_hashed_row() -> None:
    tenant_id = uuid.uuid4()
    async with tenant_session(tenant_id) as s:
        await s.execute(
            text(
                "INSERT INTO tenants (id, name, slug, webhook_secret) "
                "VALUES (:id, 'T', :slug, 'sek')"
            ),
            {"id": tenant_id, "slug": f"t-{tenant_id.hex[:10]}"},
        )
    try:
        async with tenant_session(tenant_id) as s:
            await audit.append_event(
                s,
                tenant_id=tenant_id,
                event_type="PIPELINE_COMPLETED",
                actor="system:test",
                status="completed",
                payload={"total": "100.00"},
            )
        async with tenant_session(tenant_id) as s:
            row = (
                await s.execute(
                    text(
                        "SELECT event_type, actor, payload_hash FROM audit_log "
                        "WHERE tenant_id = :t ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"t": tenant_id},
                )
            ).first()
        assert row is not None
        assert row.event_type == "PIPELINE_COMPLETED"
        assert row.actor == "system:test"
        assert row.payload_hash == audit.payload_hash({"total": "100.00"})
    finally:
        async with tenant_session(tenant_id) as s:
            await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})
