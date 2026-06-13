"""Circuit breaker unit tests (T-062)."""

from __future__ import annotations

import pytest

from app.domain.circuit_breaker import CircuitBreaker, CircuitOpenError, State


async def test_opens_after_threshold_failures() -> None:
    cb = CircuitBreaker(failure_threshold=3, window_s=60, cooldown_s=60)

    async def boom() -> None:
        raise RuntimeError("fail")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(boom)

    assert cb.state is State.OPEN
    with pytest.raises(CircuitOpenError):
        await cb.call(boom)  # short-circuited, boom not even called


async def test_success_resets_failures() -> None:
    cb = CircuitBreaker(failure_threshold=2, window_s=60, cooldown_s=60)

    async def boom() -> None:
        raise RuntimeError("fail")

    async def ok() -> int:
        return 1

    with pytest.raises(RuntimeError):
        await cb.call(boom)
    assert await cb.call(ok) == 1  # success clears the failure window
    assert cb.state is State.CLOSED


async def test_half_open_after_cooldown() -> None:
    cb = CircuitBreaker(failure_threshold=1, window_s=60, cooldown_s=0)

    async def boom() -> None:
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await cb.call(boom)
    # cooldown 0 -> immediately half-open, so a call is allowed through again
    assert cb.state is State.HALF_OPEN
