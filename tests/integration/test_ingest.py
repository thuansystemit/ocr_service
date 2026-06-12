"""Ingest API + pipeline end-to-end (T-021/023/024/025, T-033/034).

Drives a real document through: POST /extract -> documents row -> background
LangGraph run with the Postgres checkpointer -> terminal persistence -> GET. With
the Sprint 3 stub extractor, confidence is 0 so the happy path lands in the DLQ
with ``LOW_CONFIDENCE`` -- which still proves parse + guardrail + extract + score
+ route + checkpoint all ran against live Postgres.

Requires migrations 001-005 applied.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.config import get_settings
from app.db.session import tenant_session
from app.main import create_app
from app.pipeline.extraction import LLMExtraction, set_extraction_chain
from app.services import auth
from app.services.auth import generate_api_key
from tests.conftest import make_text_pdf

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("db_available")]

PDF_MIME = "application/pdf"


class _FakeChain:
    """Stand-in extraction chain so the pipeline runs without a live LLM."""

    def __init__(self, result: LLMExtraction | None = None, raises: bool = False) -> None:
        self._result = result or LLMExtraction(fields={"total": "100.00"}, confidence=0.95)
        self._raises = raises

    async def extract(self, **_: object) -> LLMExtraction:
        if self._raises:
            raise RuntimeError("simulated LLM failure")
        return self._result


async def _seed(*, with_active_schema: bool) -> tuple[uuid.UUID, str]:
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
        if with_active_schema:
            await s.execute(
                text(
                    "INSERT INTO schemas (tenant_id, name, json_schema, status, seed_count) "
                    "VALUES (:t, 'invoice', '{}'::jsonb, 'active', 3)"
                ),
                {"t": tenant_id},
            )
    return tenant_id, raw


async def _cleanup(tenant_id: uuid.UUID) -> None:
    auth._key_cache.clear()
    async with tenant_session(tenant_id) as s:
        await s.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant_id})


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def _wait_terminal(
    client: AsyncClient, doc_id: str, headers: dict, max_wait_s: float = 20.0
) -> dict:
    terminal = {"completed", "review", "rejected", "error", "cancelled"}
    deadline = asyncio.get_event_loop().time() + max_wait_s
    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] in terminal:
            return body
        await asyncio.sleep(0.25)
    raise AssertionError(f"document {doc_id} did not reach a terminal status in {max_wait_s}s")


async def test_extract_happy_path_completes() -> None:
    tenant_id, key = await _seed(with_active_schema=True)
    headers = {"Authorization": f"Bearer {key}"}
    set_extraction_chain(_FakeChain())  # type: ignore[arg-type]
    try:
        async with _client() as c:
            resp = await c.post(
                "/api/v1/extract",
                headers=headers,
                files={"file": ("invoice.pdf", make_text_pdf("Invoice 42 Total 100.00"), PDF_MIME)},
                data={"schema_name": "invoice"},
            )
            assert resp.status_code == 202, resp.text
            doc_id = resp.json()["document_id"]

            body = await _wait_terminal(c, doc_id, headers)
            assert body["status"] == "completed"  # high-confidence extraction -> STP
            assert body["routing_decision"] == "HIGH"
            assert body["extraction_result"]["extracted_json"] == {"total": "100.00"}
    finally:
        set_extraction_chain(None)
        await _cleanup(tenant_id)


async def test_extraction_failure_routes_to_dlq() -> None:
    tenant_id, key = await _seed(with_active_schema=True)
    headers = {"Authorization": f"Bearer {key}"}
    set_extraction_chain(_FakeChain(raises=True))  # type: ignore[arg-type]
    try:
        async with _client() as c:
            resp = await c.post(
                "/api/v1/extract",
                headers=headers,
                files={"file": ("invoice.pdf", make_text_pdf("Invoice 42"), PDF_MIME)},
                data={"schema_name": "invoice"},
            )
            doc_id = resp.json()["document_id"]
            body = await _wait_terminal(c, doc_id, headers)
            assert body["status"] in ("rejected", "error")

        async with tenant_session(tenant_id) as s:
            reason = (
                await s.execute(
                    text("SELECT failure_reason FROM dlq WHERE document_id = :d"), {"d": doc_id}
                )
            ).scalar_one()
        assert reason == "EXTRACTION_FAILED"
    finally:
        set_extraction_chain(None)
        await _cleanup(tenant_id)


async def test_unknown_schema_is_422() -> None:
    tenant_id, key = await _seed(with_active_schema=False)
    try:
        async with _client() as c:
            resp = await c.post(
                "/api/v1/extract",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": ("x.pdf", make_text_pdf(), PDF_MIME)},
                data={"schema_name": "nope"},
            )
        assert resp.status_code == 422
    finally:
        await _cleanup(tenant_id)


async def test_bad_mime_is_422() -> None:
    tenant_id, key = await _seed(with_active_schema=True)
    try:
        async with _client() as c:
            resp = await c.post(
                "/api/v1/extract",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": ("x.txt", b"hello", "text/plain")},
                data={"schema_name": "invoice"},
            )
        assert resp.status_code == 422
    finally:
        await _cleanup(tenant_id)


async def test_oversize_is_413() -> None:
    tenant_id, key = await _seed(with_active_schema=True)
    settings = get_settings()
    original = settings.max_file_size_bytes
    settings.max_file_size_bytes = 10  # force the limit
    try:
        async with _client() as c:
            resp = await c.post(
                "/api/v1/extract",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": ("x.pdf", make_text_pdf("way too big for 10 bytes"), PDF_MIME)},
                data={"schema_name": "invoice"},
            )
        assert resp.status_code == 413
    finally:
        settings.max_file_size_bytes = original
        await _cleanup(tenant_id)


async def test_missing_auth_is_401() -> None:
    async with _client() as c:
        resp = await c.post(
            "/api/v1/extract",
            files={"file": ("x.pdf", make_text_pdf(), PDF_MIME)},
            data={"schema_name": "invoice"},
        )
    assert resp.status_code == 401
