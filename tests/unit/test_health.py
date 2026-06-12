"""Smoke tests for the health/metrics endpoints (no DB required)."""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


async def test_metrics_exposition(client: AsyncClient) -> None:
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    # Prometheus exposition for a declared metric name should be present.
    assert "ocr_documents_ingested_total" in resp.text


async def test_openapi_served(client: AsyncClient) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    assert resp.json()["info"]["title"] == "OCR Service"
