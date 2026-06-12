"""Migration smoke tests: schema shape + audit immutability.

Verifies the 11 tables exist, RLS is enabled where expected, and the audit_log
append-only triggers actually block UPDATE/DELETE.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.db.session import get_sessionmaker, tenant_session

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("db_available")]

EXPECTED_TABLES = {
    "tenants",
    "api_keys",
    "schemas",
    "schema_versions",
    "documents",
    "extraction_results",
    "guardrail_reports",
    "review_tasks",
    "audit_log",
    "dlq",
    "webhook_deliveries",
}

RLS_TABLES = EXPECTED_TABLES - {"tenants"}


async def test_all_tables_present() -> None:
    sm = get_sessionmaker()
    async with sm() as s:
        rows = (
            (await s.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")))
            .scalars()
            .all()
        )
    present = set(rows)
    assert EXPECTED_TABLES.issubset(present), EXPECTED_TABLES - present


async def test_rls_enabled_on_tenant_tables() -> None:
    sm = get_sessionmaker()
    async with sm() as s:
        rows = (
            (
                await s.execute(
                    text(
                        """
                    SELECT relname FROM pg_class
                    WHERE relrowsecurity = true AND relnamespace = 'public'::regnamespace
                    """
                    )
                )
            )
            .scalars()
            .all()
        )
    secured = set(rows)
    assert RLS_TABLES.issubset(secured), RLS_TABLES - secured
    assert "tenants" not in secured  # root lookup table is intentionally open


async def test_audit_log_blocks_update(
    two_tenants: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant_a, _ = two_tenants
    async with tenant_session(tenant_a) as s:
        await s.execute(
            text(
                """
                INSERT INTO audit_log (tenant_id, event_type, actor)
                VALUES (:tid, 'TEST_EVENT', 'system:test')
                """
            ),
            {"tid": tenant_a},
        )

    with pytest.raises((DBAPIError, ProgrammingError)):
        async with tenant_session(tenant_a) as s:
            await s.execute(
                text("UPDATE audit_log SET actor = 'tamper' WHERE tenant_id = :tid"),
                {"tid": tenant_a},
            )


async def test_audit_log_blocks_delete(
    two_tenants: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant_a, _ = two_tenants
    async with tenant_session(tenant_a) as s:
        await s.execute(
            text(
                """
                INSERT INTO audit_log (tenant_id, event_type, actor)
                VALUES (:tid, 'TEST_EVENT', 'system:test')
                """
            ),
            {"tid": tenant_a},
        )

    with pytest.raises((DBAPIError, ProgrammingError)):
        async with tenant_session(tenant_a) as s:
            await s.execute(
                text("DELETE FROM audit_log WHERE tenant_id = :tid"),
                {"tid": tenant_a},
            )
