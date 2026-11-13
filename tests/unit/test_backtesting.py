import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from bangzen_prime.application.backtesting import (
    BacktestConfig, HistoricalCandle, TradeCandidate, evaluate_candidates,
)
from bangzen_prime.errors import DomainError


class BacktestingTest(unittest.TestCase):
    def candles(self, rows):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [
            HistoricalCandle(start + timedelta(minutes=i), *(D(str(v)) for v in row))
            for i, row in enumerate(rows)
        ]

    def test_next_candle_open_fill_and_net_costs_are_applied(self):
        candles = self.candles(
            [(100, 101, 99, 100, 10), (100, 106, 99, 105, 20),
             (105, 106, 104, 105, 20)]
        )
        candidate = TradeCandidate("a", 0, D("95"), D("110"))
        report = evaluate_candidates(candles, [candidate], BacktestConfig(
            initial_equity=D("1000"), position_notional=D("100"),
            fee_rate_per_side=D("0.001"), slippage_rate_per_side=D("0.001"),
            max_holding_candles=2,
        ))
        self.assertEqual(len(report.trades), 1)
        self.assertEqual(report.trades[0].exit_reason, "TIME_EXIT")
        self.assertLess(
            report.trades[0].net_return_pct, report.trades[0].gross_return_pct
        )

    def test_same_candle_stop_and_target_uses_stop(self):
        candles = self.candles([(100, 101, 99, 100, 10), (100, 120, 80, 105, 20)])
        report = evaluate_candidates(
            candles, [TradeCandidate("both", 0, D("90"), D("110"))]
        )
        self.assertEqual(report.trades[0].exit_reason, "STOP_LOSS")

    def test_stop_gap_exits_at_worse_open(self):
        candles = self.candles(
            [(100, 101, 99, 100, 10), (100, 102, 99, 101, 10),
             (85, 90, 80, 88, 20)]
        )
        report = evaluate_candidates(
            candles, [TradeCandidate("gap", 0, D("90"), D("120"))]
        )
        self.assertEqual(report.trades[0].exit_fill, D("85") * D("0.998"))

    def test_signal_on_last_candle_is_rejected_not_filled(self):
        candles = self.candles([(100, 101, 99, 100, 10), (101, 102, 100, 101, 10)])
        report = evaluate_candidates(
            candles, [TradeCandidate("late", 1, D("90"), D("120"))]
        )
        self.assertEqual(report.rejected_candidates, 1)
        self.assertEqual(report.trades, ())

    def test_non_monotonic_timestamps_rejected(self):
        candles = self.candles([(100, 101, 99, 100, 10), (100, 101, 99, 100, 10)])
        candles[1] = HistoricalCandle(
            candles[0].timestamp, D(100), D(101), D(99), D(100), D(10)
        )
        with self.assertRaises(DomainError):
            evaluate_candidates(candles, [])

    def test_invalid_ohlc_rejected(self):
        with self.assertRaises(DomainError):
            HistoricalCandle(
                datetime.now(timezone.utc), D(100), D(90), D(95), D(99), D(1)
            )

    def test_candidate_ids_must_be_unique(self):
        candles = self.candles([(100, 101, 99, 100, 10), (100, 101, 99, 100, 10)])
        candidate = TradeCandidate("dup", 0, D(90), D(110))
        with self.assertRaises(DomainError):
            evaluate_candidates(candles, [candidate, candidate])

    def test_report_metrics_count_wins_and_losses(self):
        candles = self.candles([(100, 101, 99, 100, 10), (100, 112, 99, 110, 20),
                                (100, 101, 99, 100, 10), (100, 101, 80, 85, 20),
                                (100, 101, 99, 100, 10)])
        candidates = [TradeCandidate("win", 0, D(90), D(110)),
                      TradeCandidate("loss", 2, D(90), D(120))]
        report = evaluate_candidates(candles, candidates, BacktestConfig(
            fee_rate_per_side=D(0), slippage_rate_per_side=D(0), max_holding_candles=1))
        self.assertEqual(report.wins, 1)
        self.assertEqual(report.losses, 1)
        self.assertEqual(report.rejected_candidates, 0)

    def test_non_integer_candidate_index_rejected(self):
        with self.assertRaises(DomainError):
            TradeCandidate("fractional", 1.5, D(90), D(110))

    def test_position_notional_cannot_exceed_initial_equity(self):
        with self.assertRaises(DomainError):
            BacktestConfig(initial_equity=D(50), position_notional=D(100))

    def test_zero_loss_sample_has_undefined_profit_factor(self):
        candles = self.candles([(100, 101, 99, 100, 10), (100, 120, 99, 115, 20)])
        report = evaluate_candidates(
            candles, [TradeCandidate("only-win", 0, D(90), D(110))]
        )
        self.assertIsNone(report.profit_factor)


if __name__ == "__main__":
    unittest.main()
