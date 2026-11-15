"""Tests for the API call budget and Decimal-only data validation. No network."""

from __future__ import annotations

import unittest
from decimal import Decimal

from bangzen_prime.core.errors import ConfigurationError
from bangzen_prime.data.api_budget import BudgetRegistry, ProviderBudget
from bangzen_prime.data.data_validation import (
    is_fresh,
    price_deviation_pct,
    prices_agree,
)


class Clock:
    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


class BudgetTests(unittest.TestCase):
    def test_calls_beyond_the_window_limit_are_denied(self):
        clock = Clock()
        reg = BudgetRegistry([ProviderBudget("solana_tracker", 3)], clock)
        self.assertEqual(
            [reg.try_acquire("solana_tracker") for _ in range(5)],
            [True, True, True, False, False],
        )

    def test_budget_refills_after_one_minute(self):
        clock = Clock()
        reg = BudgetRegistry([ProviderBudget("helius", 2)], clock)
        reg.try_acquire("helius")
        reg.try_acquire("helius")
        self.assertFalse(reg.try_acquire("helius"))
        clock.t = 59.9
        self.assertFalse(reg.try_acquire("helius"))
        clock.t = 60.0
        self.assertTrue(reg.try_acquire("helius"))

    def test_providers_are_isolated(self):
        clock = Clock()
        reg = BudgetRegistry([ProviderBudget("a", 1), ProviderBudget("b", 1)], clock)
        self.assertTrue(reg.try_acquire("a"))
        self.assertFalse(reg.try_acquire("a"))
        self.assertTrue(reg.try_acquire("b"))

    def test_unknown_provider_is_a_configuration_error_not_a_free_pass(self):
        reg = BudgetRegistry([ProviderBudget("a", 1)], Clock())
        with self.assertRaises(ConfigurationError):
            reg.try_acquire("unlisted")

    def test_invalid_budgets_are_rejected(self):
        for bad in (0, -1, True, 1.5):
            with self.subTest(bad=bad), self.assertRaises(ConfigurationError):
                ProviderBudget("x", bad)
        with self.assertRaises(ConfigurationError):
            BudgetRegistry([ProviderBudget("x", 1), ProviderBudget("x", 2)], Clock())


class ValidationTests(unittest.TestCase):
    def test_deviation_is_exact_decimal(self):
        self.assertEqual(
            price_deviation_pct(Decimal("1.00"), Decimal("1.10")), Decimal(10)
        )

    def test_boundary_is_inclusive_and_exact(self):
        self.assertTrue(prices_agree(Decimal("1.00"), Decimal("1.10"), Decimal(10)))
        self.assertFalse(
            prices_agree(Decimal("1.00"), Decimal("1.1000001"), Decimal(10))
        )

    def test_no_float_is_accepted(self):
        self.assertIsNone(price_deviation_pct(1.0, Decimal(1)))
        self.assertFalse(prices_agree(0.1 + 0.2, Decimal("0.3"), Decimal(1)))

    def test_zero_negative_and_nan_prices_never_agree(self):
        for bad in (Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(bad=bad):
                self.assertFalse(prices_agree(bad, Decimal(1), Decimal(50)))

    def test_freshness_window_and_future_timestamps(self):
        now = Decimal(1000)
        self.assertTrue(is_fresh(Decimal(940), now, 60))
        self.assertFalse(is_fresh(Decimal(939), now, 60))
        self.assertFalse(
            is_fresh(Decimal(1001), now, 60)
        )  # future observation is invalid

    def test_freshness_rejects_bad_inputs(self):
        self.assertFalse(is_fresh(1000, Decimal(1000), 60))
        self.assertFalse(is_fresh(Decimal(1000), Decimal(1000), 0))
        self.assertFalse(is_fresh(Decimal("NaN"), Decimal(1000), 60))


if __name__ == "__main__":
    unittest.main()
