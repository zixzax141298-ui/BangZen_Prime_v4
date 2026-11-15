"""Application-owned async circuit breakers for outbound use cases.

Infrastructure adapters retain their own retry/limiting primitives. This module
keeps the application dependency direction clean and provides async call semantics.
"""

from __future__ import annotations

import inspect
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bangzen_prime.core.errors import CircuitOpenError


@dataclass(frozen=True)
class ResiliencePolicy:
    """Circuit-breaker settings for one external dependency."""

    failure_threshold: int = 5
    recovery_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.recovery_seconds < 0:
            raise ValueError("recovery_seconds must not be negative")


@dataclass(frozen=True)
class ResilienceConfig:
    """Independent breaker policies; no dependency shares failure state."""

    market_breaker: ResiliencePolicy = ResiliencePolicy()
    safety_breaker: ResiliencePolicy = ResiliencePolicy()
    holder_breaker: ResiliencePolicy = ResiliencePolicy()
    intel_breaker: ResiliencePolicy = ResiliencePolicy()
    ai_breaker: ResiliencePolicy = ResiliencePolicy()


class CircuitBreaker:
    """Async-compatible fail-closed circuit breaker for an application dependency."""

    def __init__(self, name: str, policy: ResiliencePolicy) -> None:
        self.name = name
        self._threshold = policy.failure_threshold
        self._recovery_seconds = policy.recovery_seconds
        self._failures = 0
        self._state = "CLOSED"
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if (
                self._state == "OPEN"
                and time.monotonic() - self._opened_at >= self._recovery_seconds
            ):
                self._state = "HALF_OPEN"
            return self._state

    def _before_call(self) -> None:
        if self.state == "OPEN":
            raise CircuitOpenError(f"circuit open for {self.name}")

    def _record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._state == "HALF_OPEN" or self._failures >= self._threshold:
                self._state = "OPEN"
                self._opened_at = time.monotonic()
                self._failures = 0

    def _record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = "CLOSED"

    async def call(self, operation: Callable[[], Any]) -> Any:
        self._before_call()
        try:
            result = operation()
            if inspect.isawaitable(result):
                result = await result
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return result
