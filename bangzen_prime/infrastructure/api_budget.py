"""Per-provider call budget. Keeps paid API keys from being called in a tight loop.

Pure logic with an injectable clock. A call is allowed only when the provider's sliding
window has room. Denial is a normal result, never an exception, so callers can keep the
candidate in WATCH and retry on the next scheduled pass.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from bangzen_prime.errors import ConfigurationError

WINDOW_SECONDS = 60


@dataclass
class ProviderBudget:
    name: str
    calls_per_minute: int
    _stamps: deque = field(default_factory=deque, repr=False)

    def __post_init__(self) -> None:
        if not self.name or not isinstance(self.calls_per_minute, int) or isinstance(self.calls_per_minute, bool):
            raise ConfigurationError("budget needs a name and an integer calls_per_minute")
        if self.calls_per_minute <= 0:
            raise ConfigurationError("calls_per_minute must be positive")

    def _prune(self, now: float) -> None:
        while self._stamps and now - self._stamps[0] >= WINDOW_SECONDS:
            self._stamps.popleft()

    def try_acquire(self, now: float) -> bool:
        self._prune(now)
        if len(self._stamps) >= self.calls_per_minute:
            return False
        self._stamps.append(now)
        return True

    def remaining(self, now: float) -> int:
        self._prune(now)
        return self.calls_per_minute - len(self._stamps)


class BudgetRegistry:
    def __init__(self, budgets: list[ProviderBudget], clock: Callable[[], float]) -> None:
        names = [b.name for b in budgets]
        if len(names) != len(set(names)):
            raise ConfigurationError("duplicate provider budget")
        self._budgets = {b.name: b for b in budgets}
        self._clock = clock

    def try_acquire(self, provider: str) -> bool:
        if provider not in self._budgets:
            raise ConfigurationError(f"no budget configured for {provider!r}")
        return self._budgets[provider].try_acquire(self._clock())

    def remaining(self, provider: str) -> int:
        return self._budgets[provider].remaining(self._clock())
