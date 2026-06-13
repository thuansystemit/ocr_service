"""Webhook delivery (T-056/057, REQ-005/012).

POSTs the signed result to the tenant's webhook with a bounded retry schedule
([1,5,30,120,600]s, D-008). Each attempt is recorded in ``webhook_deliveries``.
On exhaustion the document goes to the DLQ with ``WEBHOOK_DELIVERY_FAILED`` and a
``WEBHOOK_EXHAUSTED`` audit event.

The HTTP client and the backoff schedule are injectable so tests run instantly
and offline; the signing core lives in ``app.domain.webhook``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DeadLetter, WebhookDelivery
from app.domain.webhook import build_signed_request
from app.observability.logging import get_logger
from app.services import audit

log = get_logger(__name__)

RETRY_SCHEDULE_S: tuple[int, ...] = (1, 5, 30, 120, 600)
_TIMEOUT_S = 10.0


class WebhookDeliverer:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        schedule: Sequence[int] = RETRY_SCHEDULE_S,
    ) -> None:
        self._client = client
        self._schedule = tuple(schedule)

    async def _post(self, url: str, body: bytes, headers: dict[str, str]) -> int:
        if self._client is not None:
            resp = await self._client.post(url, content=body, headers=headers)
            return resp.status_code
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(url, content=body, headers=headers)
            return resp.status_code

    async def deliver(
        self,
        session: AsyncSession,
        *,
        tenant_id: UUID,
        document_id: UUID,
        webhook_url: str,
        webhook_secret: str,
        payload: dict[str, Any],
    ) -> bool:
        """Attempt delivery with retries. Returns True on success.

        Records every attempt; on exhaustion writes a DLQ row + audit event. The
        first attempt is immediate; subsequent attempts wait per ``schedule``.
        """
        body, headers = build_signed_request(payload, webhook_secret)
        last_status: int | None = None

        for attempt in range(1, len(self._schedule) + 1):
            error: str | None = None
            try:
                last_status = await self._post(webhook_url, body, headers)
            except (httpx.HTTPError, OSError) as exc:
                error, last_status = str(exc), None

            session.add(
                WebhookDelivery(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    attempt=attempt,
                    http_status=last_status,
                    error=error,
                )
            )
            if last_status is not None and 200 <= last_status < 300:
                await audit.append_event(
                    session,
                    tenant_id=tenant_id,
                    document_id=document_id,
                    event_type="WEBHOOK_DELIVERED",
                    actor="system:webhook",
                    status="completed",
                    metadata={"attempt": attempt, "http_status": last_status},
                )
                return True

            if attempt < len(self._schedule):
                await asyncio.sleep(self._schedule[attempt - 1])

        # Exhausted (T-057).
        session.add(
            DeadLetter(
                document_id=document_id,
                tenant_id=tenant_id,
                failure_reason="WEBHOOK_DELIVERY_FAILED",
                last_http_status=last_status,
                status="pending",
            )
        )
        await audit.append_event(
            session,
            tenant_id=tenant_id,
            document_id=document_id,
            event_type="WEBHOOK_EXHAUSTED",
            actor="system:webhook",
            status="error",
            metadata={"attempts": len(self._schedule), "last_http_status": last_status},
        )
        log.warning("webhook.exhausted", document_id=str(document_id), last_status=last_status)
        return False
