"""LlamaParse cloud parser (C-11 primary path, T-038).

Implements the SP-002 strategy: try LlamaParse cloud with a bounded retry budget,
and on timeout / repeated 5xx / missing API key, **fall back to the local parser**
(pdfplumber → OCR) rather than failing the document. Every downgrade is recorded
in ``ParseResult.method`` so degraded parses are visible.

The cloud call (``_call_cloud``) is isolated so the retry/fallback logic is unit
-tested without hitting the network; live latency/limit validation is the
outstanding SP-002 follow-up (needs a cloud account + the I-003 decision).
"""

from __future__ import annotations

import asyncio

import httpx

from app.config import get_settings
from app.observability.logging import get_logger
from app.pipeline.parsers.base import ParseResult, clean_text
from app.pipeline.parsers.local import LocalParser

log = get_logger(__name__)

_CLOUD_BASE = "https://api.cloud.llamaindex.ai/api/v1/parsing"
_REQUEST_TIMEOUT_S = 8.0
_POLL_TIMEOUT_S = 30.0


class _CloudServerError(Exception):
    """Transient 5xx from LlamaParse cloud (retryable)."""


class LlamaParseClient:
    def __init__(self, local_fallback: LocalParser | None = None, max_retries: int = 3) -> None:
        self._fallback = local_fallback or LocalParser()
        self._max_retries = max_retries

    async def parse(self, content: bytes, *, mime_type: str | None = None) -> ParseResult:
        settings = get_settings()
        if settings.llama_cloud_api_key is None:
            return await self._fallback.parse(content, mime_type=mime_type)

        for attempt in range(1, self._max_retries + 1):
            try:
                text = await self._call_cloud(
                    content, mime_type, settings.llama_cloud_api_key.get_secret_value()
                )
                text = clean_text(text)
                return ParseResult(text=text, method="llamaparse", page_count=text.count("\f") + 1)
            except (httpx.TimeoutException, _CloudServerError) as exc:
                log.warning("parser.llamaparse.retry", attempt=attempt, error=str(exc))
                if attempt < self._max_retries:
                    await asyncio.sleep(min(2**attempt, 4))

        log.warning("parser.llamaparse.fallback_to_local")
        return await self._fallback.parse(content, mime_type=mime_type)

    async def _call_cloud(self, content: bytes, mime_type: str | None, api_key: str) -> str:
        """Upload, poll the job to completion, and return the parsed markdown.

        Raises ``_CloudServerError`` on 5xx so the caller retries; other HTTP
        errors propagate and fall through to the local fallback.
        """
        headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
            upload = await client.post(
                f"{_CLOUD_BASE}/upload",
                headers=headers,
                files={"file": ("document", content, mime_type or "application/pdf")},
            )
            if upload.status_code >= 500:
                raise _CloudServerError(f"upload {upload.status_code}")
            upload.raise_for_status()
            job_id = upload.json()["id"]

            deadline = asyncio.get_event_loop().time() + _POLL_TIMEOUT_S
            while asyncio.get_event_loop().time() < deadline:
                status_resp = await client.get(f"{_CLOUD_BASE}/job/{job_id}", headers=headers)
                if status_resp.status_code >= 500:
                    raise _CloudServerError(f"job {status_resp.status_code}")
                if status_resp.json().get("status") == "SUCCESS":
                    result = await client.get(
                        f"{_CLOUD_BASE}/job/{job_id}/result/markdown", headers=headers
                    )
                    result.raise_for_status()
                    return str(result.json().get("markdown", ""))
                await asyncio.sleep(1.0)
            raise _CloudServerError("job poll timed out")
