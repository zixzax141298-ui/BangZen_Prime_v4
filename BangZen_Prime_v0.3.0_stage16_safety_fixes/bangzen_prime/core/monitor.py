"""Continuous watchlist monitor (paper only).

Each cycle scans every watchlisted mint once, subject to a per-minute budget, records phase
transitions, and drains the outbox so accepted paper signals reach the notifier (Telegram).

Budget note: the budget counts scan attempts per minute, not each HTTP request made inside
the adapters. One scan can call several providers, so the limit is conservative by design.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from bangzen_prime.core.errors import ConfigurationError
from bangzen_prime.data.api_budget import BudgetRegistry
from bangzen_prime.discovery.tokens import validate_mint
from bangzen_prime.risk.emergency_stop import halt_flag_engaged

logger = logging.getLogger("bangzen_prime.monitor")
MAX_WATCHLIST = 200
SCAN_PROVIDERS = ("dexscreener", "rugcheck")  # providers every scan always touches


def load_watchlist(path: str | Path) -> tuple[str, ...]:
    """One mint per line. Blank lines and '#' comments are ignored. Every mint is validated."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ConfigurationError(f"cannot read watchlist: {exc.strerror}") from None
    mints: list[str] = []
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        mints.append(validate_mint(line))
    unique = tuple(dict.fromkeys(mints))
    if not unique:
        raise ConfigurationError("watchlist is empty")
    if len(unique) > MAX_WATCHLIST:
        raise ConfigurationError(f"watchlist larger than {MAX_WATCHLIST} mints")
    return unique


@dataclass(frozen=True)
class Transition:
    mint: str
    old: str
    new: str


@dataclass(frozen=True)
class CycleReport:
    cycle: int
    scanned: int
    skipped_budget: int
    accepted: int
    transitions: tuple[Transition, ...] = ()
    halted: bool = False


@dataclass
class Monitor:
    scan: object
    worker: object
    budget: BudgetRegistry
    watchlist: Sequence[str]
    chain: str = "solana"
    _last_phase: dict[str, str] = field(default_factory=dict, repr=False)
    _cycle: int = 0
    # Fail-closed kill switch. Checked before every cycle: no scan and no outbox drain while engaged.
    halt_check: Callable[[], bool] = halt_flag_engaged

    def __post_init__(self) -> None:
        self.watchlist = tuple(validate_mint(m) for m in self.watchlist)
        if not self.watchlist:
            raise ConfigurationError("monitor needs at least one mint")

    def _can_scan(self) -> bool:
        return all(self.budget.remaining(p) >= 1 for p in SCAN_PROVIDERS)

    def _spend(self) -> bool:
        """Take one unit from every provider. Returns False instead of raising mid-cycle."""
        for provider in SCAN_PROVIDERS:
            if not self.budget.try_acquire(provider):
                logger.warning("budget exhausted for %s during scan", provider)
                return False
        return True

    def _rotated(self) -> tuple[str, ...]:
        """Start each cycle at a different mint so budget shortfalls do not always hit the tail."""
        start = (self._cycle - 1) % len(self.watchlist)
        return tuple(self.watchlist[start:]) + tuple(self.watchlist[:start])

    def run_cycle(self) -> CycleReport:
        self._cycle += 1
        if self.halt_check():
            logger.warning(
                "HALT engaged: cycle %d skipped (no scans, no outbox delivery)",
                self._cycle,
            )
            return CycleReport(self._cycle, 0, 0, 0, (), halted=True)
        scanned = skipped = accepted = 0
        transitions: list[Transition] = []
        is_recent = getattr(self.scan, "is_recent", None)
        for mint in self._rotated():
            # Duplicates are answered without a provider call, so they must not spend budget.
            if is_recent is not None and is_recent(mint):
                skipped += 1
                continue
            if not self._can_scan() or not self._spend():
                skipped += 1
                continue
            result = self.scan.execute(self.chain, [mint])[0]
            scanned += 1
            if result.status == "ACCEPTED":
                accepted += 1
            # Only real observations move the phase. A None phase means nothing was observed.
            if result.phase is None:
                continue
            previous = self._last_phase.get(mint)
            if previous is not None and previous != result.phase:
                transitions.append(Transition(mint, previous, result.phase))
                logger.info(
                    "phase transition %s: %s -> %s", mint, previous, result.phase
                )
            self._last_phase[mint] = result.phase
        self.worker.run_once()
        return CycleReport(self._cycle, scanned, skipped, accepted, tuple(transitions))

    def run(
        self, *, cycles: int, interval_seconds: float, sleep: Callable[[float], None]
    ) -> list[CycleReport]:
        """cycles == 0 means run until interrupted by the operator."""
        reports: list[CycleReport] = []
        n = 0
        while cycles == 0 or n < cycles:
            reports.append(self.run_cycle())
            n += 1
            if cycles == 0 or n < cycles:
                sleep(interval_seconds)
        return reports
