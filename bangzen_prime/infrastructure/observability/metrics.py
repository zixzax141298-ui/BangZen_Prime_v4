"""In-process counters and gauges with Prometheus text exposition. Thread-safe, no dependencies."""

from __future__ import annotations

import threading
from collections import defaultdict


class Metrics:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = (
            defaultdict(float)
        )
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(name: str, labels: dict[str, str] | None):
        if not name.replace("_", "").isalnum():
            raise ValueError("metric names must be alphanumeric with underscores")
        return name, tuple(sorted((labels or {}).items()))

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        if value < 0:
            raise ValueError("counters cannot decrease")
        with self._lock:
            self._counters[self._key(name, labels)] += value

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._gauges[self._key(name, labels)] = float(value)

    def value(self, name: str, **labels: str) -> float:
        key = self._key(name, labels)
        with self._lock:
            return self._counters.get(key, self._gauges.get(key, 0.0))

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for store, kind in ((self._counters, "counter"), (self._gauges, "gauge")):
                for name in sorted({k[0] for k in store}):
                    lines.append(f"# TYPE {name} {kind}")
                    for (metric, labels), v in sorted(store.items()):
                        if metric != name:
                            continue
                        label_text = ",".join(
                            f'{k}="{_escape(val)}"' for k, val in labels
                        )
                        suffix = f"{{{label_text}}}" if label_text else ""
                        lines.append(f"{name}{suffix} {v:g}")
        return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
