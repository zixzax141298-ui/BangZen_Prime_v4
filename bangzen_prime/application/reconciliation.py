# bangzen_prime/infrastructure/resilience.py
from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TypeVar

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

from bangzen_prime.application.heartbeat import EmergencyLatch
from bangzen_prime.domain.shared import ensure_utc
from bangzen_prime.errors import ExternalServiceError
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.infrastructure.persistence.sqlite.outbox import AuditLog

T = TypeVar("T")
logger = logging.getLogger("bangzen_prime.resilience")


class CircuitOpenError(RuntimeError):
    pass


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True)
class ResiliencePolicy:
    failure_threshold: int = 5
    slow_call_threshold_seconds: float = 3.0
    minimum_calls: int = 10
    failure_rate: float = 0.5
    recovery_seconds: float = 30.0
    half_open_probes: int = 2
    max_attempts: int = 3
    base_backoff_seconds: float = 0.25
    max_backoff_seconds: float = 5.0
    retryable_status_codes: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass
class CircuitBreaker:
    name: str
    policy: ResiliencePolicy = field(default_factory=ResiliencePolicy)
    state: CircuitState = CircuitState.CLOSED
    _recent: list[bool] = field(default_factory=list)
    _opened_at: float = 0.0
    _half_open_successes: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def call(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        fallback: Callable[[Exception], Awaitable[T]] | None = None,
    ) -> T:
        async with self._lock:
            if self.state is CircuitState.OPEN:
                if time.monotonic() - self._opened_at < self.policy.recovery_seconds:
                    if fallback is None:
                        raise CircuitOpenError(f"{self.name} circuit is open")
                    return await fallback(CircuitOpenError(f"{self.name} circuit is open"))
                self.state = CircuitState.HALF_OPEN
                self._half_open_successes = 0

        try:
            started = time.monotonic()
            result = await asyncio.wait_for(
                operation(),
                timeout=self.policy.slow_call_threshold_seconds * 3,
            )
            elapsed = time.monotonic() - started
        except Exception as exc:
            await self._record_failure(exc)
            if fallback is not None:
                return await fallback(exc)
            raise
        else:
            await self._record_success(elapsed)
            return result

    async def _record_success(self, elapsed: float) -> None:
        async with self._lock:
            if self.state is CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.policy.half_open_probes:
                    self.state = CircuitState.CLOSED
                    self._recent.clear()
                return

            self._recent.append(elapsed <= self.policy.slow_call_threshold_seconds)
            if len(self._recent) > self.policy.minimum_calls:
                self._recent.pop(0)

            if len(self._recent) >= self.policy.minimum_calls:
                success_rate = sum(self._recent) / len(self._recent)
                if success_rate < 1 - self.policy.failure_rate:
                    self._open()

    async def _record_failure(self, exc: Exception) -> None:
        async with self._lock:
            if self.state is CircuitState.HALF_OPEN:
                self._open()
                return

            self._recent.append(False)
            if len(self._recent) > self.policy.minimum_calls:
                self._recent.pop(0)

            failures = self._recent.count(False)
            if failures >= self.policy.failure_threshold:
                self._open()

    def _open(self) -> None:
        self.state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        logger.warning("circuit opened", extra={"circuit": self.name})


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: ResiliencePolicy,
    is_retryable: Callable[[Exception], bool] | None = None,
) -> T:
    delay = policy.base_backoff_seconds

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            retryable = is_retryable(exc) if is_retryable else True
            if not retryable or attempt == policy.max_attempts:
                raise

            jitter = random.uniform(0, delay)
            await asyncio.sleep(min(delay + jitter, policy.max_backoff_seconds))
            delay = min(delay * 2, policy.max_backoff_seconds)

    raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------
# Balance reconciliation worker (read-only; trips the emergency latch on mismatch)
#
# Expected units are the sum of filled units of open orders for the mint. A mismatch
# beyond tolerance trips the latch. An unavailable or invalid balance never counts as OK
# and does not trip the latch, because an outage is not evidence of a mismatch.
# ---------------------------------------------------------------------------

OPEN_STATUSES = ("FILLED", "PARTIALLY_FILLED")
STATUS_NOT_CONFIGURED = "NOT_CONFIGURED"
STATUS_OK = "OK"
STATUS_MISMATCH = "MISMATCH"
STATUS_UNAVAILABLE = "UNAVAILABLE"


class BalanceProvider(Protocol):
    def token_balance(self, owner: str, mint: str) -> Decimal: ...


@dataclass(frozen=True)
class ReconciliationResult:
    status: str
    mint: str
    expected_units: Decimal | None
    observed_units: Decimal | None
    reason: str


class ReconciliationWorker:
    def __init__(
        self,
        *,
        db: Database,
        balances: BalanceProvider | None,
        owner: str,
        tolerance_pct: Decimal,
        latch: EmergencyLatch,
    ) -> None:
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("an owner address is required")
        if not isinstance(tolerance_pct, Decimal) or not tolerance_pct.is_finite():
            raise ValueError("tolerance must be a finite Decimal")
        if not Decimal("0") <= tolerance_pct <= Decimal("100"):
            raise ValueError("tolerance must be within [0, 100] percent")
        self._db = db
        self._balances = balances
        self._owner = owner.strip()
        self._tolerance = tolerance_pct
        self._latch = latch

    def expected_units(self, mint: str) -> Decimal:
        """Units still held by open orders for this mint. No open orders means zero."""
        placeholders = ",".join("?" for _ in OPEN_STATUSES)
        rows = self._db.query_all(
            "SELECT o.filled_units AS units FROM orders o"
            " JOIN tokens t ON t.id = o.token_id"
            f" WHERE t.mint = ? AND o.status IN ({placeholders})",
            (mint, *OPEN_STATUSES),
        )
        total = Decimal("0")
        for row in rows:
            total += Decimal(str(row["units"]))
        return total

    def run_once(self, mint: str, at: datetime) -> ReconciliationResult:
        at = ensure_utc(at)
        if self._balances is None:
            return ReconciliationResult(STATUS_NOT_CONFIGURED, mint, None, None, "NOT_CONFIGURED")

        expected = self.expected_units(mint)
        try:
            observed = self._balances.token_balance(self._owner, mint)
        except ExternalServiceError:
            return ReconciliationResult(STATUS_UNAVAILABLE, mint, expected, None, "BALANCE_UNAVAILABLE")

        if not isinstance(observed, Decimal):
            try:
                observed = Decimal(str(observed))
            except (InvalidOperation, ValueError):
                return ReconciliationResult(STATUS_UNAVAILABLE, mint, expected, None, "BALANCE_INVALID")
        if not observed.is_finite() or observed < 0:
            return ReconciliationResult(STATUS_UNAVAILABLE, mint, expected, None, "BALANCE_INVALID")

        allowed = expected * self._tolerance / Decimal("100")
        if abs(observed - expected) <= allowed:
            return ReconciliationResult(STATUS_OK, mint, expected, observed, "WITHIN_TOLERANCE")

        reason = f"RECONCILIATION_MISMATCH:{mint[:8]}"
        self._latch.trigger(reason, at)
        with self._db.transaction() as conn:
            AuditLog(conn).append(
                "ReconciliationMismatch",
                {
                    "mint": mint,
                    "expected_units": str(expected),
                    "observed_units": str(observed),
                    "tolerance_pct": str(self._tolerance),
                },
                at,
            )
        return ReconciliationResult(STATUS_MISMATCH, mint, expected, observed, reason)
