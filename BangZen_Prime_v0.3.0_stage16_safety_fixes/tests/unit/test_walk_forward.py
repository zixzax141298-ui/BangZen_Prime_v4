import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from bangzen_prime.core.errors import DomainError
from bangzen_prime.research.backtesting import (
    BacktestConfig,
    HistoricalCandle,
    TradeCandidate,
)
from bangzen_prime.research.walk_forward import (
    buy_and_hold_net_pnl,
    chronological_split,
    run_walk_forward,
)

START = datetime(2026, 1, 1, tzinfo=UTC)


def _flat(count: int, price: str = "100") -> list[HistoricalCandle]:
    p = D(price)
    return [
        HistoricalCandle(START + timedelta(minutes=i), p, p + 1, p - 1, p, D(10))
        for i in range(count)
    ]


def _rising(count: int) -> list[HistoricalCandle]:
    out = []
    for i in range(count):
        o = D(100 + i)
        out.append(
            HistoricalCandle(START + timedelta(minutes=i), o, o + 1, o - 1, o + 1, D(10))
        )
    return out


class ChronologicalSplitTest(unittest.TestCase):
    def test_phases_are_contiguous_and_test_is_latest(self):
        split = chronological_split(100)
        self.assertEqual((split.development.start, split.development.end), (0, 50))
        self.assertEqual((split.validation.start, split.validation.end), (50, 75))
        self.assertEqual((split.test.start, split.test.end), (75, 100))

    def test_rejects_invalid_fractions_and_short_series(self):
        with self.assertRaises(DomainError):
            chronological_split(100, development_fraction=D("0.8"), validation_fraction=D("0.3"))
        with self.assertRaises(DomainError):
            chronological_split(100, development_fraction=D(0))
        with self.assertRaises(DomainError):
            chronological_split(30)  # fewer than 3 * 20 candles
        with self.assertRaises(DomainError):
            chronological_split(100.0)  # type: ignore[arg-type]


class BaselineTest(unittest.TestCase):
    def test_buy_and_hold_on_flat_series_loses_only_costs(self):
        config = BacktestConfig(
            position_notional=D(100),
            fee_rate_per_side=D("0.001"),
            slippage_rate_per_side=D("0.002"),
        )
        pnl = buy_and_hold_net_pnl(_flat(10), config)
        self.assertLess(pnl, D(0))
        # entry 100 * 1.002, exit 100 * 0.998; fees on both sides
        units = D(100) / (D(100) * D("1.002"))
        proceeds = units * (D(100) * D("0.998")) * D("0.999")
        cash_in = D(100) * D("1.001")
        self.assertEqual(pnl, proceeds - cash_in)

    def test_buy_and_hold_on_rising_series_is_positive(self):
        config = BacktestConfig(position_notional=D(100))
        self.assertGreater(buy_and_hold_net_pnl(_rising(20), config), D(0))


class RunWalkForwardTest(unittest.TestCase):
    def setUp(self):
        self.candles = _flat(200)
        self.candidates = [
            TradeCandidate(f"c{i}", i, D(95), D(110)) for i in range(0, 199, 3)
        ]
        self.config = BacktestConfig()

    def test_each_candidate_belongs_to_exactly_one_phase(self):
        report = run_walk_forward(self.candles, self.candidates, self.config)
        total = sum(phase.candidate_count for phase in report.phases)
        self.assertEqual(total, len(self.candidates))
        self.assertEqual([p.phase for p in report.phases], ["development", "validation", "test"])

    def test_identical_inputs_produce_identical_report(self):
        first = run_walk_forward(self.candles, self.candidates, self.config)
        second = run_walk_forward(self.candles, self.candidates, self.config)
        self.assertEqual(first, second)
        self.assertEqual(len(first.config_hash), 64)

    def test_config_hash_changes_when_costs_change(self):
        base = run_walk_forward(self.candles, self.candidates, self.config)
        changed = run_walk_forward(
            self.candles,
            self.candidates,
            BacktestConfig(fixed_cost_per_trade=D("0.5")),
        )
        self.assertNotEqual(base.config_hash, changed.config_hash)

    def test_strategy_on_flat_data_does_not_beat_no_trade(self):
        report = run_walk_forward(self.candles, self.candidates, self.config)
        test = report.phase("test")
        self.assertFalse(test.beats_no_trade)
        self.assertFalse(test.beats_buy_and_hold)

    def test_folds_partition_test_phase_and_report_missing_trades_as_no_evidence(self):
        report = run_walk_forward(self.candles, [], self.config, fold_count=4)
        self.assertEqual(len(report.folds), 4)
        self.assertEqual(report.folds[0].start, report.split.test.start)
        self.assertEqual(report.folds[-1].end, report.split.test.end)
        self.assertIsNone(report.positive_fold_ratio)
        self.assertTrue(all(f.expectancy_pct is None for f in report.folds))

    def test_rejects_candidate_outside_candle_range(self):
        bad = self.candidates + [TradeCandidate("late", 500, D(95), D(110))]
        with self.assertRaises(DomainError):
            run_walk_forward(self.candles, bad, self.config)

    def test_rejects_duplicate_candidate_ids_across_phases(self):
        dup = [TradeCandidate("same", 1, D(95), D(110)), TradeCandidate("same", 150, D(95), D(110))]
        with self.assertRaises(DomainError):
            run_walk_forward(self.candles, dup, self.config)

    def test_rejects_split_that_does_not_cover_all_candles(self):
        split = chronological_split(150)
        with self.assertRaises(DomainError):
            run_walk_forward(self.candles, self.candidates, self.config, split=split)

    def test_fold_count_must_be_at_least_two(self):
        with self.assertRaises(DomainError):
            run_walk_forward(self.candles, self.candidates, self.config, fold_count=1)


if __name__ == "__main__":
    unittest.main()
