"""Per-tenant rate limiter unit tests (T-019)."""

from __future__ import annotations

import uuid

import pytest

from app.services.rate_limit import QueueFullError, TenantRateLimiter


async def test_acquire_up_to_limit_then_rejects() -> None:
    limiter = TenantRateLimiter()
    tenant = uuid.uuid4()

    await limiter.acquire(tenant, limit=2)
    await limiter.acquire(tenant, limit=2)
    assert limiter.inflight(tenant) == 2

    with pytest.raises(QueueFullError):
        await limiter.acquire(tenant, limit=2)


async def test_release_frees_a_slot() -> None:
    limiter = TenantRateLimiter()
    tenant = uuid.uuid4()
    await limiter.acquire(tenant, limit=1)
    await limiter.release(tenant)
    assert limiter.inflight(tenant) == 0
    await limiter.acquire(tenant, limit=1)  # slot is free again


async def test_tenants_are_independent() -> None:
    limiter = TenantRateLimiter()
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    await limiter.acquire(t1, limit=1)
    await limiter.acquire(t2, limit=1)  # t2 not blocked by t1
    assert limiter.inflight(t1) == 1
    assert limiter.inflight(t2) == 1
