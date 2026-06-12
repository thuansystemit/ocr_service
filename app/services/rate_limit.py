"""Per-tenant in-flight rate limiting (T-019, REQ-035).

Bounds how many documents a single tenant may have in the pipeline at once
(``tenants.max_queue_size``). When the bound is hit, ingest returns HTTP 429 with
``Retry-After`` rather than unbounded queueing. The counter is per-process
in-memory; with multiple API replicas each enforces a share of the limit, which
is acceptable for backpressure (a hard global cap would need Redis -- deferred).
"""

from __future__ import annotations

import asyncio
from uuid import UUID


class QueueFullError(Exception):
    """Raised when a tenant is at its in-flight limit."""

    def __init__(self, retry_after_s: int = 5) -> None:
        super().__init__("tenant queue is full")
        self.retry_after_s = retry_after_s


class TenantRateLimiter:
    def __init__(self) -> None:
        self._inflight: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, tenant_id: UUID | str, limit: int) -> None:
        tid = str(tenant_id)
        async with self._lock:
            current = self._inflight.get(tid, 0)
            if current >= limit:
                raise QueueFullError()
            self._inflight[tid] = current + 1

    async def release(self, tenant_id: UUID | str) -> None:
        tid = str(tenant_id)
        async with self._lock:
            current = self._inflight.get(tid, 0)
            if current <= 1:
                self._inflight.pop(tid, None)
            else:
                self._inflight[tid] = current - 1

    def inflight(self, tenant_id: UUID | str) -> int:
        return self._inflight.get(str(tenant_id), 0)


_limiter: TenantRateLimiter | None = None


def get_rate_limiter() -> TenantRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = TenantRateLimiter()
    return _limiter
