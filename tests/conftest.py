"""Shared test fixtures.

Unit tests run with no external dependencies. Integration tests (marked
``@pytest.mark.integration``) require a live Postgres reachable via
``OCR_DATABASE_URL`` with migrations applied (``make migrate`` or the CI
service). The ``db_available`` fixture skips them cleanly when Postgres is down.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import dispose_engine, get_engine, tenant_session
from app.main import create_app


def make_text_pdf(text_content: str = "Invoice 12345 Total 99.00") -> bytes:
    """Build a tiny single-page PDF with a real embedded text layer.

    Byte-accurate (correct xref offsets) so pdfplumber/pdfminer parse it without
    recovery warnings. Shared by parser and ingest tests.
    """
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = b"BT /F1 24 Tf 72 700 Td (" + text_content.encode() + b") Tj ET"
    objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    pdf = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref_pos = len(pdf)
    pdf += b"xref\n0 %d\n" % (len(objs) + 1)
    pdf += b"0000000000 65535 f \n"
    for off in offsets:
        pdf += b"%010d 00000 n \n" % off
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        len(objs) + 1,
        xref_pos,
    )
    return pdf


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An httpx client wired to the ASGI app (no network)."""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await dispose_engine()


@pytest.fixture
async def db_available() -> AsyncIterator[None]:
    """Skip the test if Postgres is not reachable."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Postgres not available: {exc.__class__.__name__}")
    yield
    await dispose_engine()


@pytest.fixture
async def two_tenants() -> AsyncIterator[tuple[uuid.UUID, uuid.UUID]]:
    """Create two tenants and clean them up afterwards.

    tenants has no RLS, so we can insert/delete it within a tenant session.
    Cleanup cascades to all tenant-scoped child rows.
    """
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    insert = text(
        """
        INSERT INTO tenants (id, name, slug, webhook_secret)
        VALUES (:id, :name, :slug, 'test-secret')
        """
    )
    async with tenant_session(tenant_a) as s:
        await s.execute(insert, {"id": tenant_a, "name": "A", "slug": f"a-{tenant_a.hex[:8]}"})
        await s.execute(insert, {"id": tenant_b, "name": "B", "slug": f"b-{tenant_b.hex[:8]}"})

    yield tenant_a, tenant_b

    async with tenant_session(tenant_a) as s:
        await s.execute(
            text("DELETE FROM tenants WHERE id = ANY(:ids)"),
            {"ids": [tenant_a, tenant_b]},
        )
