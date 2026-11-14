"""Worker supervisor: isolates failures, disables repeat offenders, honours emergency stop,
and shuts down gracefully (the current cycle finishes; no new cycle starts).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from bangzen_prime.infrastructure.observability.metrics import Metrics

logger = logging.getLogger("bangzen_prime.supervisor")


@dataclass
class WorkerSpec:
    name: str
    run: Callable[[], object]
    places_orders: bool = False
    consecutive_failures: int = 0
    disabled: bool = False
    last_status: str = "NEW"


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

    def request_stop(self) -> None:
        self._stop.set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def run_cycle(self) -> dict[str, str]:
        results: dict[str, str] = {}
        stop_now = self.emergency_stop()
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
            try:
                worker.run()
            except Exception as exc:  # noqa: BLE001 - isolation boundary
                worker.consecutive_failures += 1
                results[worker.name] = "FAILED"
                self.metrics.inc("bangzen_worker_failures_total", worker=worker.name)
                logger.error("worker %s failed: %s", worker.name, type(exc).__name__)
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
