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

from bangzen_prime.domain.tokens import validate_mint
from bangzen_prime.errors import ConfigurationError
from bangzen_prime.infrastructure.api_budget import BudgetRegistry

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


@dataclass
class Monitor:
    scan: object
    worker: object
    budget: BudgetRegistry
    watchlist: Sequence[str]
    chain: str = "solana"
    _last_phase: dict[str, str] = field(default_factory=dict, repr=False)
    _cycle: int = 0

    def __post_init__(self) -> None:
        self.watchlist = tuple(validate_mint(m) for m in self.watchlist)
        if not self.watchlist:
            raise ConfigurationError("monitor needs at least one mint")

    def _can_scan(self) -> bool:
        return all(self.budget.remaining(p) >= 1 for p in SCAN_PROVIDERS)

    def _spend(self) -> None:
        for provider in SCAN_PROVIDERS:
            if not self.budget.try_acquire(
                provider
            ):  # pragma: no cover - guarded by _can_scan
                raise ConfigurationError(f"budget exhausted for {provider}")

    def run_cycle(self) -> CycleReport:
        self._cycle += 1
        scanned = skipped = accepted = 0
        transitions: list[Transition] = []
        for mint in self.watchlist:
            if not self._can_scan():
                skipped += 1
                continue
            self._spend()
            result = self.scan.execute(self.chain, [mint])[0]
            scanned += 1
            if result.status == "ACCEPTED":
                accepted += 1
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
