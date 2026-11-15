"""Memory watermark for long-running workers.

Returns UNKNOWN when resident memory cannot be read on this platform. UNKNOWN is never
reported as OK, and the supervisor logs it. This guard limits operational load only. It is
not a trading safety gate.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

OK: Final = "OK"
OVER_LIMIT: Final = "OVER_LIMIT"
UNKNOWN: Final = "UNKNOWN"


def current_rss_mb(proc_status: str = "/proc/self/status") -> float | None:
    """Resident set size in MiB from /proc, or None if it cannot be read."""
    try:
        with open(proc_status, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return int(parts[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        return None
    return None


def memory_status(
    limit_mb: float, reader: Callable[[], float | None] = current_rss_mb
) -> str:
    if limit_mb <= 0:
        raise ValueError("limit_mb must be positive")
    rss = reader()
    if rss is None:
        return UNKNOWN
    return OVER_LIMIT if rss > limit_mb else OK
