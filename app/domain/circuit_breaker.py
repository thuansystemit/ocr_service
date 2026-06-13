"""Async circuit breaker (C-19, T-062, REQ-046/047).

Per-process breaker around a flaky dependency (the primary LLM). After
``failure_threshold`` failures within ``window_s`` it OPENs; while OPEN, calls
short-circuit so the caller can fall back (to GPT-4o) without hammering the
failing provider. After ``cooldown_s`` it half-opens and a success closes it.

Per-process (not shared) by design (D-009): no Redis dependency, and each worker
replica protecting itself is sufficient for provider-outage backpressure.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

from app.observability.logging import get_logger

log = get_logger(__name__)

T = TypeVar("T")


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the breaker is OPEN."""


class CircuitBreaker:
    def __init__(
        self,
        *,
        name: str = "llm",
        failure_threshold: int = 5,
        window_s: float = 60.0,
        cooldown_s: float = 60.0,
    ) -> None:
        self.name = name
        self._threshold = failure_threshold
        self._window = window_s
        self._cooldown = cooldown_s
        self._failures: list[float] = []
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> State:
        if self._opened_at is None:
            return State.CLOSED
        if time.monotonic() - self._opened_at >= self._cooldown:
            return State.HALF_OPEN
        return State.OPEN

    async def _record_failure(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._failures = [t for t in self._failures if now - t < self._window]
            self._failures.append(now)
            if len(self._failures) >= self._threshold and self._opened_at is None:
                self._opened_at = now
                log.critical(
                    "circuit_breaker.open", breaker=self.name, failures=len(self._failures)
                )

    async def _record_success(self) -> None:
        async with self._lock:
            self._failures.clear()
            if self._opened_at is not None:
                log.info("circuit_breaker.closed", breaker=self.name)
            self._opened_at = None

    async def call(self, fn: Callable[[], Awaitable[T]]) -> T:
        """Run ``fn`` under the breaker. Raises ``CircuitOpenError`` if OPEN."""
        if self.state is State.OPEN:
            raise CircuitOpenError(f"circuit '{self.name}' is open")
        try:
            result = await fn()
        except Exception:
            await self._record_failure()
            raise
        await self._record_success()
        return result
