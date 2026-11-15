"""Heartbeats, watchdog, and the emergency-stop latch.

The latch is one-way: once triggered it stays active until an operator calls `reset`, and every
trigger and reset is recorded through the audit callback. The watchdog triggers the latch when
any expected worker has not beaten for longer than its timeout (default 5 seconds).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timedelta

from bangzen_prime.core.shared import ensure_utc


class HeartbeatRegistry:
    def __init__(self) -> None:
        self._last: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def beat(self, name: str, at: datetime) -> None:
        with self._lock:
            self._last[name] = ensure_utc(at)

    def last(self, name: str) -> datetime | None:
        with self._lock:
            return self._last.get(name)


class EmergencyLatch:
    def __init__(
        self, audit: Callable[[str, dict, datetime], None] | None = None
    ) -> None:
        self._active = False
        self._reason: str | None = None
        self._audit = audit or (lambda event, payload, at: None)
        self._lock = threading.Lock()

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    @property
    def reason(self) -> str | None:
        with self._lock:
            return self._reason

    def trigger(self, reason: str, at: datetime) -> bool:
        """Activate the latch. Returns True only on the first activation."""
        with self._lock:
            if self._active:
                return False
            self._active = True
            self._reason = reason[:200]
        self._audit("EmergencyStopTriggered", {"reason": self._reason}, ensure_utc(at))
        return True

    def reset(self, *, operator: str, at: datetime) -> None:
        if not operator.strip():
            raise ValueError("an operator name is required to reset the emergency stop")
        with self._lock:
            was_active = self._active
            self._active = False
            self._reason = None
        if was_active:
            self._audit(
                "EmergencyStopReset",
                {"operator": operator.strip()[:64]},
                ensure_utc(at),
            )


class Watchdog:
    def __init__(
        self,
        *,
        registry: HeartbeatRegistry,
        expected: tuple[str, ...],
        timeout: timedelta,
        latch: EmergencyLatch,
    ) -> None:
        if timeout <= timedelta(0):
            raise ValueError("watchdog timeout must be positive")
        self._registry = registry
        self._expected = tuple(expected)
        self._timeout = timeout
        self._latch = latch

    def stale_workers(self, now: datetime) -> list[str]:
        now = ensure_utc(now)
        stale = []
        for name in self._expected:
            last = self._registry.last(name)
            if last is None or now - last > self._timeout:
                stale.append(name)
        return stale

    def check(self, now: datetime) -> list[str]:
        stale = self.stale_workers(now)
        if stale:
            self._latch.trigger("WATCHDOG_STALE:" + ",".join(sorted(stale)), now)
        return stale
