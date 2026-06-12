"""Per-tenant async worker pool (C-17, D-012).

Concurrency is bounded *per tenant* via a semaphore map so one noisy tenant
cannot starve others of pipeline slots. The pool itself is transport-agnostic:
it just runs awaitable jobs under the right tenant's semaphore. Sprint 3+ wires
the LangGraph pipeline runner in as the job body.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar
from uuid import UUID

from app.config import get_settings
from app.observability.logging import bind_context, clear_context, get_logger

log = get_logger(__name__)

T = TypeVar("T")


class WorkerPool:
    """Bounds concurrency per tenant using one semaphore per tenant_id."""

    def __init__(self, default_concurrency: int | None = None) -> None:
        self._default = default_concurrency or get_settings().worker_default_concurrency
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._limits: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def _semaphore_for(self, tenant_id: str) -> asyncio.Semaphore:
        async with self._lock:
            sem = self._semaphores.get(tenant_id)
            if sem is None:
                limit = self._limits.get(tenant_id, self._default)
                sem = asyncio.Semaphore(limit)
                self._semaphores[tenant_id] = sem
            return sem

    def set_tenant_limit(self, tenant_id: UUID | str, limit: int) -> None:
        """Override concurrency for a tenant. Takes effect on next semaphore creation."""
        if limit < 1:
            raise ValueError("limit must be >= 1")
        tid = str(tenant_id)
        self._limits[tid] = limit
        # Drop any existing semaphore so the new limit is picked up.
        self._semaphores.pop(tid, None)

    async def submit(
        self,
        tenant_id: UUID | str,
        job: Callable[[], Awaitable[T]],
        *,
        document_id: str | None = None,
    ) -> T:
        """Run ``job`` under the tenant's concurrency limit and return its result.

        Logging context (tenant_id/document_id) is bound for the duration so all
        pipeline log lines are correlated.
        """
        tid = str(tenant_id)
        sem = await self._semaphore_for(tid)
        async with sem:
            bind_context(tenant_id=tid, document_id=document_id)
            try:
                log.debug("worker.job.start")
                result = await job()
                log.debug("worker.job.done")
                return result
            except Exception:
                log.exception("worker.job.failed")
                raise
            finally:
                clear_context()

    def stats(self) -> dict[str, int]:
        """Approximate available slots per tenant (for diagnostics/metrics)."""
        return {tid: sem._value for tid, sem in self._semaphores.items()}


_pool: WorkerPool | None = None


def get_worker_pool() -> WorkerPool:
    global _pool
    if _pool is None:
        _pool = WorkerPool()
    return _pool
