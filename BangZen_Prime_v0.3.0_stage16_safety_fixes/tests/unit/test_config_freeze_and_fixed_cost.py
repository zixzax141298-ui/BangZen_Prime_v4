import unittest
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from bangzen_prime.core.errors import DomainError
from bangzen_prime.research.backtesting import (
    BacktestConfig,
    HistoricalCandle,
    TradeCandidate,
    evaluate_candidates,
)
from bangzen_prime.research.config_freeze import canonical_json, config_hash


@dataclass(frozen=True)
class _Sample:
    rate: D
    name: str


class ConfigFreezeTest(unittest.TestCase):
    def test_equal_decimal_values_hash_the_same_regardless_of_text_form(self):
        self.assertEqual(config_hash(_Sample(D("0.001"), "a")), config_hash(_Sample(D("0.0010"), "a")))
        self.assertEqual(config_hash({"x": D("1000")}), config_hash({"x": D("1E+3")}))

    def test_any_value_change_changes_the_hash(self):
        self.assertNotEqual(config_hash(_Sample(D("0.001"), "a")), config_hash(_Sample(D("0.002"), "a")))

    def test_key_order_does_not_matter(self):
        self.assertEqual(canonical_json({"b": 1, "a": 2}), canonical_json({"a": 2, "b": 1}))

    def test_floats_are_rejected(self):
        with self.assertRaises(DomainError):
            config_hash({"rate": 0.001})

    def test_naive_datetimes_are_rejected(self):
        with self.assertRaises(DomainError):
            config_hash({"when": datetime(2026, 1, 1)})
        self.assertIn("2026-01-01", canonical_json({"when": datetime(2026, 1, 1, tzinfo=UTC)}))

    def test_non_finite_decimals_are_rejected(self):
        with self.assertRaises(DomainError):
            config_hash({"x": D("NaN")})

    def test_backtest_config_hash_is_stable(self):
        self.assertEqual(config_hash(BacktestConfig()), config_hash(BacktestConfig()))


class FixedCostPerTradeTest(unittest.TestCase):
    def setUp(self):
        start = datetime(2026, 1, 1, tzinfo=UTC)
        self.candles = [
            HistoricalCandle(start + timedelta(minutes=i), D(100), D(106), D(99), D(105), D(10))
            for i in range(5)
        ]
        self.candidate = [TradeCandidate("a", 0, D(95), D(110))]

    def test_default_fixed_cost_is_zero_and_leaves_results_unchanged(self):
        default = evaluate_candidates(self.candles, self.candidate, BacktestConfig())
        explicit = evaluate_candidates(self.candles, self.candidate,
                                       BacktestConfig(fixed_cost_per_trade=D(0)))
        self.assertEqual(default, explicit)

    def test_fixed_cost_reduces_net_pnl_by_exactly_that_amount(self):
        base = evaluate_candidates(self.candles, self.candidate, BacktestConfig())
        costly = evaluate_candidates(self.candles, self.candidate,
                                     BacktestConfig(fixed_cost_per_trade=D("0.5")))
        self.assertEqual(base.trades[0].net_pnl - costly.trades[0].net_pnl, D("0.5"))

    def test_negative_fixed_cost_is_rejected(self):
        with self.assertRaises(DomainError):
            BacktestConfig(fixed_cost_per_trade=D("-0.1"))


if __name__ == "__main__":
    unittest.main()
