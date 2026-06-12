"""LlamaParse client retry + fallback unit tests (T-038)."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import SecretStr

from app.config import get_settings
from app.pipeline.parsers.base import ParseResult
from app.pipeline.parsers.llamaparse import LlamaParseClient, _CloudServerError


class _FakeFallback:
    async def parse(self, content: bytes, *, mime_type: str | None = None) -> ParseResult:
        return ParseResult(text="fallback text", method="local", page_count=1)


@pytest.fixture(autouse=True)
def _reset_key() -> None:
    yield
    get_settings().llama_cloud_api_key = None


async def test_no_api_key_uses_local_fallback() -> None:
    get_settings().llama_cloud_api_key = None
    client = LlamaParseClient(local_fallback=_FakeFallback())  # type: ignore[arg-type]
    result = await client.parse(b"data")
    assert result.method == "local"
    assert result.text == "fallback text"


async def test_success_uses_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings().llama_cloud_api_key = SecretStr("k")
    client = LlamaParseClient(local_fallback=_FakeFallback())  # type: ignore[arg-type]

    async def fake_cloud(content: bytes, mime: str | None, key: str) -> str:
        return "cloud markdown body"

    monkeypatch.setattr(client, "_call_cloud", fake_cloud)
    result = await client.parse(b"data")
    assert result.method == "llamaparse"
    assert "cloud markdown body" in result.text


async def test_5xx_retries_then_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_sleep(*_: object) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)
    get_settings().llama_cloud_api_key = SecretStr("k")
    client = LlamaParseClient(local_fallback=_FakeFallback(), max_retries=3)  # type: ignore[arg-type]
    calls = {"n": 0}

    async def failing(content: bytes, mime: str | None, key: str) -> str:
        calls["n"] += 1
        raise _CloudServerError("500")

    monkeypatch.setattr(client, "_call_cloud", failing)
    result = await client.parse(b"data")
    assert calls["n"] == 3  # retried up to the budget
    assert result.method == "local"  # then fell back
