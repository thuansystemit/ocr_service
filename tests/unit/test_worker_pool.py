"""Worker pool concurrency tests."""

from __future__ import annotations

import asyncio
import uuid

from app.worker.pool import WorkerPool


async def test_runs_job_and_returns_result() -> None:
    pool = WorkerPool(default_concurrency=5)

    async def job() -> int:
        return 42

    assert await pool.submit(uuid.uuid4(), job) == 42


async def test_per_tenant_concurrency_is_bounded() -> None:
    """A tenant limited to 2 never runs more than 2 jobs at once."""
    pool = WorkerPool(default_concurrency=2)
    tenant = uuid.uuid4()
    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def job() -> None:
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(0.02)
        async with lock:
            active -= 1

    await asyncio.gather(*(pool.submit(tenant, job) for _ in range(10)))
    assert peak <= 2


async def test_separate_tenants_have_independent_limits() -> None:
    pool = WorkerPool(default_concurrency=1)
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    started = asyncio.Event()
    release = asyncio.Event()
    order: list[str] = []

    async def hold(tag: str) -> None:
        order.append(tag)
        started.set()
        await release.wait()

    task1 = asyncio.create_task(pool.submit(t1, lambda: hold("t1")))
    await asyncio.wait_for(started.wait(), timeout=1)
    # t2 should not be blocked by t1's saturated semaphore.
    task2 = asyncio.create_task(pool.submit(t2, lambda: hold("t2")))
    await asyncio.sleep(0.02)
    assert "t2" in order
    release.set()
    await asyncio.gather(task1, task2)
