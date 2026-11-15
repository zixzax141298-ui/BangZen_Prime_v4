"""Persist discovery cooldowns across restarts (scheduling hint only).

A cooldown only decides when a candidate is scanned again. It is not a blacklist, and it
never grants or blocks a trade. Losing or corrupting the file therefore means a re-scan, not
a trading decision, so unreadable content is treated as "no cooldowns".

Expiries are stored as UNIX epoch seconds, because monotonic clocks reset on restart.
Writes are atomic (temporary file, then os.replace), so a crash cannot leave a half-written
file behind.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger("bangzen_prime.discovery.cooldown")

_FORMAT_VERSION = 1


class CooldownStore:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def load(self, now_epoch: float) -> dict[str, float]:
        """Return mint -> expiry epoch for entries still in the future."""
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            logger.warning("cooldown file unreadable; starting with no cooldowns")
            return {}
        if not isinstance(raw, dict) or raw.get("version") != _FORMAT_VERSION:
            logger.warning("cooldown file has an unknown format; starting with no cooldowns")
            return {}
        entries = raw.get("entries")
        if not isinstance(entries, dict):
            return {}
        result: dict[str, float] = {}
        for mint, expiry in entries.items():
            if isinstance(mint, str) and isinstance(expiry, (int, float)) and not isinstance(expiry, bool):
                if float(expiry) > now_epoch:
                    result[mint] = float(expiry)
        return result

    def save(self, entries: dict[str, float], now_epoch: float) -> None:
        """Atomically write the cooldowns that are still active."""
        live = {mint: float(exp) for mint, exp in entries.items() if float(exp) > now_epoch}
        payload = json.dumps({"version": _FORMAT_VERSION, "entries": live}, sort_keys=True)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self._path.parent, prefix=".cooldown-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self._path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
