import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

from bangzen_prime.core.errors import DomainError
from bangzen_prime.research.backtesting import BacktestConfig
from bangzen_prime.research.config_freeze import config_hash
from bangzen_prime.research.forward_paper import ForwardPaperLedger, ForwardTrade
from bangzen_prime.research.readiness_gate import (
    STATUS_HUMAN_REVIEW,
    DataCoverage,
    GateThresholds,
    evaluate_readiness,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
CFG = config_hash(BacktestConfig())


def _trade(i: int, pnl: str, phase: str = "EXPANSION", hours: int = 1, start_h: int = 0) -> ForwardTrade:
    opened = T0 + timedelta(hours=start_h + i)
    return ForwardTrade(
        trade_id=f"p{i}",
        lifecycle_phase=phase,
        opened_at=opened,
        closed_at=opened + timedelta(hours=hours),
        notional=D(100),
        net_pnl=D(pnl),
        net_return_pct=D(pnl),
        exit_reason="TAKE_PROFIT" if D(pnl) > 0 else "STOP_LOSS",
    )


class ForwardPaperLedgerTest(unittest.TestCase):
    def test_trade_from_different_config_is_refused(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        with self.assertRaises(DomainError):
            ledger.record(_trade(0, "1"), "f" * 64)

    def test_duplicate_trade_id_is_refused(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        ledger.record(_trade(0, "1"), CFG)
        with self.assertRaises(DomainError):
            ledger.record(_trade(0, "2"), CFG)

    def test_closed_before_opened_is_refused(self):
        with self.assertRaises(DomainError):
            ForwardTrade("x", "EXPANSION", T0 + timedelta(hours=1), T0, D(1), D(0), D(0), "TIME_EXIT")

    def test_naive_timestamps_and_unknown_phase_are_refused(self):
        with self.assertRaises(DomainError):
            ForwardTrade("x", "EXPANSION", datetime(2026, 1, 1), T0, D(1), D(0), D(0), "TIME_EXIT")
        with self.assertRaises(DomainError):
            ForwardTrade("x", "moon", T0, T0 + timedelta(hours=1), D(1), D(0), D(0), "TIME_EXIT")

    def test_hash_chain_detects_edited_trade(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        for i, pnl in enumerate(["5", "-2", "3"]):
            ledger.record(_trade(i, pnl), CFG)
        self.assertTrue(ledger.verify_chain())
        tampered = ledger.entries[1]
        ledger.entries[1] = type(tampered)(
            index=tampered.index,
            prev_hash=tampered.prev_hash,
            entry_hash=tampered.entry_hash,
            trade=_trade(1, "50"),
        )
        self.assertFalse(ledger.verify_chain())

    def test_save_and_load_round_trip_preserves_chain(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        ledger.record(_trade(0, "5"), CFG)
        ledger.record(_trade(1, "-2", phase="LAUNCH"), CFG)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "forward.jsonl"
            ledger.save(path)
            loaded = ForwardPaperLedger.load(path)
            self.assertEqual(loaded.config_hash, CFG)
            self.assertEqual(loaded.entries, ledger.entries)
            lines = path.read_text(encoding="utf-8").splitlines()
            tampered = lines[2].replace('"-2"', '"-20"')
            self.assertNotEqual(tampered, lines[2])
            path.write_text("\n".join([lines[0], lines[1], tampered]) + "\n", encoding="utf-8")
            with self.assertRaises(DomainError):
                ForwardPaperLedger.load(path)


class ForwardMetricsTest(unittest.TestCase):
    def test_metrics_match_hand_computed_values(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        ledger.record(_trade(0, "10", phase="LAUNCH", hours=2), CFG)
        ledger.record(_trade(1, "-5", phase="EXPANSION", hours=1), CFG)
        ledger.record(_trade(2, "5", phase="EXPANSION", hours=1), CFG)
        m = ledger.metrics(T0, T0 + timedelta(hours=10))
        self.assertEqual(m.trade_count, 3)
        self.assertEqual(m.expectancy_pct, D(10) / 3)
        self.assertEqual(m.win_rate_pct, D(200) / 3)
        self.assertEqual(m.profit_factor, D(3))  # gross profit 15 / gross loss 5
        self.assertEqual(m.exposure_pct, D(4) / D(10) * D(100))  # 4h held in 10h window
        self.assertEqual(m.mean_holding_seconds, D(4 * 3600) / 3)
        self.assertEqual(m.per_phase["LAUNCH"], 1)
        self.assertEqual(m.per_phase["EXPANSION"], 2)

    def test_drawdown_uses_realised_equity_curve(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        ledger.record(_trade(0, "-100"), CFG)  # equity 900
        ledger.record(_trade(1, "50"), CFG)    # equity 950, peak 1000 still
        ledger.record(_trade(2, "-200"), CFG)  # equity 750, drawdown from 1000 = 25%
        m = ledger.metrics(T0, T0 + timedelta(hours=10))
        self.assertEqual(m.max_drawdown_pct, D(25))

    def test_empty_ledger_reports_no_values_not_zeros(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        m = ledger.metrics(T0, T0 + timedelta(hours=1))
        self.assertEqual(m.trade_count, 0)
        self.assertIsNone(m.expectancy_pct)
        self.assertIsNone(m.max_drawdown_pct)
        self.assertIsNone(ledger.summary_for_gate())

    def test_no_losses_means_profit_factor_undefined(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        ledger.record(_trade(0, "5"), CFG)
        self.assertIsNone(ledger.metrics(T0, T0 + timedelta(hours=5)).profit_factor)

    def test_window_must_be_positive(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        with self.assertRaises(DomainError):
            ledger.metrics(T0, T0)


class ForwardPaperGateIntegrationTest(unittest.TestCase):
    def test_summary_carries_frozen_hash_so_gate_can_match_it(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        ledger.record(_trade(0, "5"), CFG)
        summary = ledger.summary_for_gate()
        self.assertIsNotNone(summary)
        self.assertEqual(summary.config_hash, CFG)
        self.assertEqual(summary.trade_count, 1)

    def test_gate_still_blocks_when_forward_sample_is_small(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        ledger.record(_trade(0, "5"), CFG)
        decision = evaluate_readiness(None, None, DataCoverage(True, True, True, True, True), ledger.summary_for_gate())
        self.assertNotEqual(decision.status, STATUS_HUMAN_REVIEW)
        self.assertIn("forward_paper_sample", decision.blockers)
        self.assertFalse(decision.live_trading_allowed)
        self.assertEqual(GateThresholds().min_forward_paper_trades, 50)


if __name__ == "__main__":
    unittest.main()
