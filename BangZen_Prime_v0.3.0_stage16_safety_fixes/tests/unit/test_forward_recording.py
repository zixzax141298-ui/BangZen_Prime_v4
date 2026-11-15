import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from bangzen_prime.core.errors import DomainError
from bangzen_prime.execution.forward_recording import (
    forward_trade_from_order,
    sync_closed_orders,
)
from bangzen_prime.execution.orders import OrderStatus
from bangzen_prime.execution.simulated import OrderRecord
from bangzen_prime.research.backtesting import BacktestConfig
from bangzen_prime.research.config_freeze import config_hash
from bangzen_prime.research.forward_paper import ForwardPaperLedger

T0 = datetime(2026, 1, 1, tzinfo=UTC)
CFG = config_hash(BacktestConfig())


def _order(i: int, *, status=OrderStatus.CLOSED, pnl="4", exit_price="110", closed=True) -> OrderRecord:
    return OrderRecord(
        id=f"o{i}",
        idempotency_key=f"k{i}",
        signal_id=f"s{i}",
        token_id="tok",
        token_mint="mint",
        status=status,
        requested_units=D(1),
        filled_units=D(1),
        entry_price=D(100),
        fill_price=D(100),
        stop_loss=D(95),
        take_profit=D(110),
        entry_fee=D("0.1"),
        exit_price=D(exit_price) if closed else None,
        exit_fee=D("0.1") if closed else None,
        realized_pnl=D(pnl) if closed else None,
        created_at=T0 + timedelta(hours=i),
        closed_at=(T0 + timedelta(hours=i, minutes=30)) if closed else None,
    )


class ForwardRecordingTest(unittest.TestCase):
    def test_closed_order_maps_to_net_forward_trade(self):
        trade = forward_trade_from_order(_order(1))
        self.assertEqual(trade.trade_id, "o1")
        self.assertEqual(trade.net_pnl, D("4"))
        self.assertEqual(trade.notional, D(100))
        self.assertEqual(trade.net_return_pct, D("4"))
        self.assertEqual(trade.exit_reason, "TAKE_PROFIT")
        self.assertEqual(trade.lifecycle_phase, "UNKNOWN")

    def test_stop_exit_is_labelled_and_phase_is_not_guessed(self):
        trade = forward_trade_from_order(_order(2, pnl="-6", exit_price="94"), "LAUNCH")
        self.assertEqual(trade.exit_reason, "STOP_LOSS")
        self.assertEqual(trade.lifecycle_phase, "LAUNCH")

    def test_open_order_is_refused(self):
        with self.assertRaises(DomainError):
            forward_trade_from_order(_order(3, status=OrderStatus.FILLED, closed=False))

    def test_closed_order_missing_pnl_is_refused_not_zeroed(self):
        order = _order(4)
        broken = OrderRecord(**{**order.__dict__, "realized_pnl": None})
        with self.assertRaises(DomainError):
            forward_trade_from_order(broken)

    def test_sync_is_idempotent_and_skips_open_orders(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        orders = [_order(1), _order(2, pnl="-1", exit_price="99"), _order(3, status=OrderStatus.FILLED, closed=False)]
        self.assertEqual(sync_closed_orders(ledger, orders), 2)
        self.assertEqual(sync_closed_orders(ledger, orders), 0)
        self.assertEqual(len(ledger.entries), 2)
        self.assertTrue(ledger.verify_chain())

    def test_synced_orders_feed_the_gate_summary_with_frozen_hash(self):
        ledger = ForwardPaperLedger(CFG, D(1000))
        sync_closed_orders(ledger, [_order(1), _order(2, pnl="-1", exit_price="99")])
        summary = ledger.summary_for_gate()
        self.assertEqual(summary.trade_count, 2)
        self.assertEqual(summary.config_hash, CFG)


if __name__ == "__main__":
    unittest.main()
