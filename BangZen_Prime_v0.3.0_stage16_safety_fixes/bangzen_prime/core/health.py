"""Health report for operators (Termux and VPS). Read-only; it changes no state.

Status precedence: HALTED (HALT.flag or emergency stop) > DEGRADED (disabled worker, stale
heartbeat, or memory over limit) > OK. Unknown memory is reported as UNKNOWN and does not
by itself make the status DEGRADED.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from bangzen_prime.core import resource_guard
from bangzen_prime.core.heartbeat import HeartbeatRegistry
from bangzen_prime.core.supervisor import Supervisor
from bangzen_prime.risk.emergency_stop import HALT_FLAG_PATH, halt_engaged

HALTED = "HALTED"
DEGRADED = "DEGRADED"
OK = "OK"


@dataclass(frozen=True)
class HealthReport:
    status: str
    halt_engaged: bool
    disabled_workers: tuple[str, ...]
    stale_workers: tuple[str, ...]
    memory: str
    worker_status: dict[str, str]

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "halt_engaged": self.halt_engaged,
            "disabled_workers": list(self.disabled_workers),
            "stale_workers": list(self.stale_workers),
            "memory": self.memory,
            "worker_status": dict(self.worker_status),
        }


def build_health(
    supervisor: Supervisor,
    *,
    now: datetime,
    emergency_stop: bool = False,
    halt_path: str = HALT_FLAG_PATH,
    heartbeats: HeartbeatRegistry | None = None,
    stale_after: timedelta = timedelta(minutes=10),
    memory_limit_mb: float | None = None,
    rss_reader: Callable[[], float | None] = resource_guard.current_rss_mb,
) -> HealthReport:
    if stale_after <= timedelta(0):
        raise ValueError("stale_after must be positive")
    halted = halt_engaged(emergency_stop, halt_path)
    disabled = tuple(w.name for w in supervisor.workers if w.disabled)
    stale: list[str] = []
    if heartbeats is not None:
        for worker in supervisor.workers:
            last = heartbeats.last(worker.name)
            if last is None or now - last > stale_after:
                stale.append(worker.name)
    memory = (
        resource_guard.memory_status(memory_limit_mb, rss_reader)
        if memory_limit_mb is not None
        else resource_guard.UNKNOWN
    )
    if halted:
        status = HALTED
    elif disabled or stale or memory == resource_guard.OVER_LIMIT:
        status = DEGRADED
    else:
        status = OK
    return HealthReport(
        status=status,
        halt_engaged=halted,
        disabled_workers=disabled,
        stale_workers=tuple(stale),
        memory=memory,
        worker_status={w.name: w.last_status for w in supervisor.workers},
    )
