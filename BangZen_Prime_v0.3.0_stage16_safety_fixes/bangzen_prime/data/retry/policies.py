"""Resilience primitives. Time is injected so tests never sleep."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TypeVar

from bangzen_prime.core.errors import CircuitOpenError, ExternalServiceError

T = TypeVar("T")


class Clock:
    """Wall clock. Replace with FakeClock in tests."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        import time

        return time.monotonic()


class FakeClock(Clock):
    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)
        self._mono = 0.0
        self._lock = threading.Lock()

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._now += timedelta(seconds=seconds)
            self._mono += seconds


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("delays must not be negative")

    def delay_for(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None and retry_after >= 0:
            return min(retry_after, self.max_delay_seconds)
        return min(
            self.base_delay_seconds * (2 ** (attempt - 1)), self.max_delay_seconds
        )


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_seconds: float = 30.0,
        clock: Clock | None = None,
    ) -> None:
        self.name = name
        self._threshold = failure_threshold
        self._recovery = recovery_seconds
        self._clock = clock or Clock()
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state is CircuitState.OPEN and (
                self._clock.monotonic() - self._opened_at >= self._recovery
            ):
                self._state = CircuitState.HALF_OPEN
            return self._state

    def before_call(self) -> None:
        if self.state is CircuitState.OPEN:
            raise CircuitOpenError(f"circuit open for {self.name}")

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._trip()
                return
            self._failures += 1
            if self._failures >= self._threshold:
                self._trip()

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock.monotonic()
        self._failures = 0


class TokenBucket:
    """Blocking-free limiter: `acquire` returns False when the bucket is empty."""

    def __init__(
        self,
        *,
        rate_per_minute: float,
        capacity: float | None = None,
        clock: Clock | None = None,
    ) -> None:
        if rate_per_minute <= 0:
            raise ValueError("rate_per_minute must be positive")
        self._rate = rate_per_minute / 60.0
        self._capacity = capacity if capacity is not None else rate_per_minute
        self._tokens = float(self._capacity)
        self._clock = clock or Clock()
        self._last = self._clock.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            now = self._clock.monotonic()
            self._tokens = min(
                self._capacity, self._tokens + (now - self._last) * self._rate
            )
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


@dataclass
class HealthMonitor:
    """Counts outcomes per dependency; consulted by callers and exposed to status commands."""

    successes: dict[str, int] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, name: str, ok: bool) -> None:
        with self._lock:
            bucket = self.successes if ok else self.failures
            bucket[name] = bucket.get(name, 0) + 1

    def snapshot(self) -> dict[str, dict[str, int]]:
        with self._lock:
            names = set(self.successes) | set(self.failures)
            return {
                n: {"ok": self.successes.get(n, 0), "failed": self.failures.get(n, 0)}
                for n in sorted(names)
            }


class ResilientCaller:
    """Wraps one outbound dependency with limiter, breaker, retries and health tracking."""

    def __init__(
        self,
        name: str,
        *,
        retry: RetryPolicy,
        limiter: TokenBucket,
        breaker: CircuitBreaker,
        health: HealthMonitor,
        sleep: Callable[[float], None],
        clock: Clock | None = None,
    ) -> None:
        self.name = name
        self._retry = retry
        self._limiter = limiter
        self._breaker = breaker
        self._health = health
        self._sleep = sleep
        self._clock = clock or Clock()

    def call(self, fn: Callable[[], T]) -> T:
        attempt = 0
        while True:
            attempt += 1
            self._breaker.before_call()
            if not self._limiter.acquire():
                self._health.record(self.name, ok=False)
                raise ExternalServiceError(
                    f"rate limit reached for {self.name}",
                    service=self.name,
                    retryable=True,
                    status=429,
                )
            try:
                result = fn()
            except ExternalServiceError as exc:
                self._health.record(self.name, ok=False)
                if exc.retryable:
                    self._breaker.record_failure()
                if not exc.retryable or attempt >= self._retry.max_attempts:
                    raise
                self._sleep(self._retry.delay_for(attempt, exc.retry_after))
                continue
            self._breaker.record_success()
            self._health.record(self.name, ok=True)
            return result
