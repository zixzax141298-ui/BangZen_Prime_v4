"""Continuous candidate discovery with phase-aware, result-sensitive retry timing."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from bangzen_prime.core.use_cases import ScanMarketUseCase, ScanResult
from bangzen_prime.core.errors import DomainError, HaltEngagedError
from bangzen_prime.discovery.cooldown_store import CooldownStore
from bangzen_prime.discovery.lifecycle import LifecycleObservation, LifecyclePhase
from bangzen_prime.discovery.tokens import validate_mint

logger = logging.getLogger("bangzen_prime.discovery")

_RETRY_SOON_REASONS = frozenset(
    {
        "EMPTY_MARKET",
        "MARKET_UNAVAILABLE",
        "SAFETY_UNAVAILABLE",
        "STALE_MARKET",
        "INSUFFICIENT_HISTORY",
        "AI_UNAVAILABLE",
        "AI_OUTPUT_INVALID",
    }
)


class DiscoveryFeed(Protocol):
    def fetch_candidates(self, limit: int = 30) -> list[str]: ...


class LifecycleRegistry(Protocol):
    def observe(self, observation: LifecycleObservation) -> bool: ...


@dataclass(frozen=True)
class DiscoveryCycle:
    discovered: int
    scanned: int
    skipped_recent: int
    results: tuple[ScanResult, ...]


class ContinuousDiscoveryUseCase:
    """Revisit immature or temporarily unavailable candidates sooner.

    This is a process-local scheduling hint, not a blacklist or permanent rejection.
    It does not change any trade authorization or safety gate.
    """

    def __init__(
        self,
        *,
        feed: DiscoveryFeed,
        scanner: ScanMarketUseCase,
        clock: Callable[[], float] = time.monotonic,
        dedupe_seconds: int = 1800,
        retry_seconds: int = 60,
        lifecycle_registry: LifecycleRegistry | None = None,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        cooldown_store: CooldownStore | None = None,
        epoch_clock: Callable[[], float] = time.time,
        halt_check: Callable[[], bool] | None = None,
    ) -> None:
        self._halt_check = halt_check
        if dedupe_seconds < 0:
            raise ValueError("dedupe_seconds must not be negative")
        if retry_seconds < 1:
            raise ValueError("retry_seconds must be positive")
        self._feed = feed
        self._scanner = scanner
        self._clock = clock
        self._dedupe_seconds = dedupe_seconds
        self._retry_seconds = min(retry_seconds, dedupe_seconds)
        self._lifecycle_registry = lifecycle_registry
        self._wall_clock = wall_clock
        self._cooldown_store = cooldown_store
        self._epoch_clock = epoch_clock
        self._recent: dict[str, float] = {}
        if cooldown_store is not None:
            # Stored expiries are epoch seconds; convert them to this process's monotonic clock.
            now_mono = clock()
            now_epoch = epoch_clock()
            for mint, expiry_epoch in cooldown_store.load(now_epoch).items():
                self._recent[mint] = now_mono + (expiry_epoch - now_epoch)

    def _raise_if_halted(self) -> None:
        if self._halt_check is not None and self._halt_check():
            raise HaltEngagedError("emergency stop engaged; discovery halted")

    def execute(self, *, limit: int = 20) -> DiscoveryCycle:
        if not 1 <= limit <= 100:
            raise ValueError("discovery limit must be within [1, 100]")
        self._raise_if_halted()
        now = self._clock()
        self._recent = {
            mint: expires_at
            for mint, expires_at in self._recent.items()
            if expires_at > now
        }
        candidates = self._feed.fetch_candidates(limit=limit)
        unique: list[str] = []
        for candidate in dict.fromkeys(candidates):
            try:
                unique.append(validate_mint(candidate))
            except DomainError:
                logger.warning(
                    "discovery feed returned an invalid Solana mint; candidate skipped"
                )

        if self._lifecycle_registry is not None and unique:
            observed_at = self._wall_clock()
            for mint in unique:
                self._lifecycle_registry.observe(
                    LifecycleObservation(
                        chain="solana",
                        mint=mint,
                        phase=LifecyclePhase.DISCOVERED,
                        observed_at=observed_at,
                        reason="DISCOVERY_FEED",
                        evidence={"feed": "dexscreener_latest_profiles"},
                    )
                )

        fresh = [mint for mint in unique if mint not in self._recent]
        self._raise_if_halted()
        results = self._scanner.execute("solana", fresh) if fresh else []
        by_mint = {result.mint: result for result in results}

        for mint in fresh:
            result = by_mint.get(mint)
            retry_soon = result is None or bool(
                _RETRY_SOON_REASONS.intersection(result.reasons)
            )
            cooldown = self._retry_seconds if retry_soon else self._dedupe_seconds
            if cooldown > 0:
                self._recent[mint] = now + cooldown

        if self._cooldown_store is not None:
            epoch_now = self._epoch_clock()
            self._cooldown_store.save(
                {mint: epoch_now + (expires_at - now) for mint, expires_at in self._recent.items()},
                epoch_now,
            )

        logger.info(
            "discovery cycle complete: discovered=%d scanned=%d skipped_recent=%d",
            len(unique),
            len(results),
            len(unique) - len(fresh),
        )
        return DiscoveryCycle(
            discovered=len(unique),
            scanned=len(results),
            skipped_recent=len(unique) - len(fresh),
            results=tuple(results),
        )
