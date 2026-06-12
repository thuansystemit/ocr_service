"""RLS adversarial suite (SP-004) -- the #1 risk: cross-tenant data leakage.

These prove the database itself enforces tenant isolation under the ``ocr_app``
role, independent of any application-layer filtering:

  1. A tenant only sees its own rows.
  2. A tenant cannot read another tenant's rows even knowing their ids.
  3. A tenant cannot forge a row for another tenant (WITH CHECK).
  4. With no tenant context set, tenant-scoped tables are inaccessible.

Requires live Postgres with migrations 001-003 applied, connected as ``ocr_app``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.db.session import get_sessionmaker, tenant_session

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("db_available")]


async def _insert_api_key(tenant_id: uuid.UUID) -> uuid.UUID:
    key_id = uuid.uuid4()
    async with tenant_session(tenant_id) as s:
        await s.execute(
            text(
                """
                INSERT INTO api_keys (id, tenant_id, key_hash, key_prefix)
                VALUES (:id, :tid, :hash, :prefix)
                """
            ),
            {"id": key_id, "tid": tenant_id, "hash": uuid.uuid4().hex, "prefix": "ocr_test"},
        )
    return key_id


async def test_tenant_sees_only_own_rows(
    two_tenants: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant_a, tenant_b = two_tenants
    await _insert_api_key(tenant_a)
    await _insert_api_key(tenant_a)
    await _insert_api_key(tenant_b)

    async with tenant_session(tenant_a) as s:
        count_a = (await s.execute(text("SELECT count(*) FROM api_keys"))).scalar_one()
    async with tenant_session(tenant_b) as s:
        count_b = (await s.execute(text("SELECT count(*) FROM api_keys"))).scalar_one()

    assert count_a == 2
    assert count_b == 1


async def test_cannot_read_other_tenant_row_by_id(
    two_tenants: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant_a, tenant_b = two_tenants
    key_id = await _insert_api_key(tenant_a)

    async with tenant_session(tenant_b) as s:
        row = (
            await s.execute(text("SELECT id FROM api_keys WHERE id = :id"), {"id": key_id})
        ).first()
    assert row is None  # RLS hides it even with the exact id


async def test_cannot_forge_row_for_other_tenant(
    two_tenants: tuple[uuid.UUID, uuid.UUID],
) -> None:
    tenant_a, tenant_b = two_tenants
    # In tenant B's context, try to write a row owned by tenant A.
    with pytest.raises((DBAPIError, ProgrammingError)):
        async with tenant_session(tenant_b) as s:
            await s.execute(
                text(
                    """
                    INSERT INTO api_keys (tenant_id, key_hash, key_prefix)
                    VALUES (:tid, :hash, 'forge')
                    """
                ),
                {"tid": tenant_a, "hash": uuid.uuid4().hex},
            )


async def test_no_tenant_context_blocks_access() -> None:
    """Without SET LOCAL app.current_tenant_id, the policy predicate errors out
    rather than leaking rows -- a safe-by-default failure."""
    sm = get_sessionmaker()
    with pytest.raises((DBAPIError, ProgrammingError)):
        async with sm() as s:
            async with s.begin():
                await s.execute(text("SELECT count(*) FROM api_keys"))
