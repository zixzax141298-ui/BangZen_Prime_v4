"""Worker supervisor: isolates failures, disables repeat offenders, honours emergency stop,
and shuts down gracefully (the current cycle finishes; no new cycle starts).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from bangzen_prime.core import resource_guard
from bangzen_prime.core.observability.metrics import Metrics

logger = logging.getLogger("bangzen_prime.supervisor")


@dataclass
class WorkerSpec:
    name: str
    run: Callable[[], object]
    places_orders: bool = False
    consecutive_failures: int = 0
    disabled: bool = False
    last_status: str = "NEW"
    next_allowed_at: float = 0.0


@dataclass
class Supervisor:
    workers: list[WorkerSpec]
    emergency_stop: Callable[[], bool]
    metrics: Metrics
    sleep: Callable[[float], None]
    max_consecutive_failures: int = 3
    beat: Callable[[str], None] | None = None
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    cycles: int = 0
    # Off by default, so existing behaviour is unchanged. When enabled, a failed worker waits
    # base * 2**(failures-1) seconds (capped) before it runs again.
    clock: Callable[[], float] = time.monotonic
    backoff_base_seconds: float = 0.0
    backoff_max_seconds: float = 300.0
    # Off by default. When the resident set exceeds the limit, non-order workers are skipped.
    # Workers that place orders are never skipped for memory reasons; emergency stop still
    # applies to them.
    memory_limit_mb: float | None = None
    rss_reader: Callable[[], float | None] = resource_guard.current_rss_mb

    def __post_init__(self) -> None:
        if self.backoff_base_seconds < 0 or self.backoff_max_seconds < 0:
            raise ValueError("backoff values must not be negative")
        if self.memory_limit_mb is not None and self.memory_limit_mb <= 0:
            raise ValueError("memory_limit_mb must be positive when set")

    def _backoff_for(self, failures: int) -> float:
        if self.backoff_base_seconds <= 0:
            return 0.0
        return min(self.backoff_base_seconds * (2 ** (failures - 1)), self.backoff_max_seconds)

    def request_stop(self) -> None:
        self._stop.set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def run_cycle(self) -> dict[str, str]:
        results: dict[str, str] = {}
        stop_now = self.emergency_stop()
        over_memory = False
        if self.memory_limit_mb is not None:
            status = resource_guard.memory_status(self.memory_limit_mb, self.rss_reader)
            over_memory = status == resource_guard.OVER_LIMIT
            if status == resource_guard.UNKNOWN:
                logger.warning("memory usage unavailable on this platform; no memory limit applied")
            elif over_memory:
                logger.warning("memory above %.0f MiB; non-order workers paused", self.memory_limit_mb)
        now = self.clock()
        for worker in self.workers:
            if worker.disabled:
                results[worker.name] = "DISABLED"
                continue
            if worker.places_orders and stop_now:
                results[worker.name] = "SKIPPED_EMERGENCY_STOP"
                self.metrics.inc(
                    "bangzen_worker_skipped_total",
                    worker=worker.name,
                    reason="emergency_stop",
                )
                continue
            if over_memory and not worker.places_orders:
                results[worker.name] = "SKIPPED_MEMORY"
                self.metrics.inc(
                    "bangzen_worker_skipped_total", worker=worker.name, reason="memory"
                )
                continue
            if now < worker.next_allowed_at:
                results[worker.name] = "BACKOFF"
                continue
            try:
                worker.run()
            except Exception as exc:  # noqa: BLE001 - isolation boundary
                worker.consecutive_failures += 1
                results[worker.name] = "FAILED"
                self.metrics.inc("bangzen_worker_failures_total", worker=worker.name)
                logger.error("worker %s failed: %s", worker.name, type(exc).__name__)
                delay = self._backoff_for(worker.consecutive_failures)
                if delay > 0:
                    worker.next_allowed_at = self.clock() + delay
                if worker.consecutive_failures >= self.max_consecutive_failures:
                    worker.disabled = True
                    self.metrics.set_gauge(
                        "bangzen_worker_disabled", 1, worker=worker.name
                    )
                    logger.error(
                        "worker %s disabled after repeated failures", worker.name
                    )
            else:
                worker.consecutive_failures = 0
                results[worker.name] = "OK"
                if self.beat is not None:
                    self.beat(worker.name)
                self.metrics.inc("bangzen_worker_runs_total", worker=worker.name)
            worker.last_status = results[worker.name]
        self.cycles += 1
        self.metrics.set_gauge("bangzen_supervisor_cycles", self.cycles)
        return results

    def run(
        self, *, interval_seconds: float = 5.0, max_cycles: int | None = None
    ) -> int:
        while not self._stop.is_set():
            self.run_cycle()
            if self._stop.is_set():
                break
            if max_cycles is not None and self.cycles >= max_cycles:
                break
            self.sleep(interval_seconds)
        return self.cycles
