"""Default provider budgets. Override with the scan rate; each scan spends one slot per provider."""

from __future__ import annotations

from collections.abc import Callable

from bangzen_prime.infrastructure.api_budget import BudgetRegistry, ProviderBudget


def default_budget_registry(
    clock: Callable[[], float], *, scans_per_minute: int
) -> BudgetRegistry:
    return BudgetRegistry(
        [
            ProviderBudget("dexscreener", scans_per_minute),
            ProviderBudget("rugcheck", scans_per_minute),
        ],
        clock,
    )
