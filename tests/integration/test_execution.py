import os
import tempfile
import unittest
from decimal import Decimal

from bangzen_prime.domain.orders import OrderStatus, transition
from bangzen_prime.domain.signals import PriceLevels, Signal
from bangzen_prime.domain.tokens import PairSnapshot, Token
from bangzen_prime.errors import ConfigurationError, DomainError
from bangzen_prime.infrastructure.adapters.execution.simulated import (
    FaultPlan,
    OrderCommand,
    SimulatedExecution,
)
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.infrastructure.persistence.sqlite.repositories import UnitOfWork
from tests.support import PAIR_ADDRESS, START, TOKEN_MINT, clock_at

D = Decimal
LEVELS = PriceLevels(D("2"), D("1.8"), D("2.3"))


def setup_db(path=":memory:"):
    db = Database(path)
    db.migrate()
    uow = UnitOfWork(db)
    token = Token(chain="solana", mint=TOKEN_MINT, symbol="T")
    pair = PairSnapshot.create(
        chain="solana",
        pair_address=PAIR_ADDRESS,
        dex_id="raydium",
        base_mint=TOKEN_MINT,
        base_symbol="T",
        price_usd="2",
        liquidity_usd="50000",
        volume_24h_usd="1",
        observed_at=START,
    )
    signal = Signal.accept(
        token_id=token.id,
        pair_id=pair.pair_id,
        score=D(60),
        confidence=D("0.6"),
        levels=LEVELS,
        created_at=START,
    )
    with uow.begin() as repos:
        repos.tokens.upsert(token, START)
        repos.pairs.upsert(pair)
        repos.signals.add(signal)
    return db, token, signal


def execution(
    db, faults=None, clock=None, fee="0.001", slip="0.005", paper=True, dry=True
):
    return SimulatedExecution(
        db=db,
        fee_rate=D(fee),
        slippage_rate=D(slip),
        clock=(clock or clock_at(0)).now,
        paper=paper,
        dry_run=dry,
        faults=faults,
    )


def command(token, signal, key=None, size="10"):
    return OrderCommand(
        idempotency_key=key or f"open:{signal.id}",
        signal_id=signal.id,
        token_id=token.id,
        levels=LEVELS,
        size_units=D(size),
        token_mint=TOKEN_MINT,
    )


class StateMachineTest(unittest.TestCase):
    def test_legal_transitions(self):
        self.assertEqual(
            transition(OrderStatus.NEW, OrderStatus.FILLED), OrderStatus.FILLED
        )
        self.assertEqual(
            transition(OrderStatus.FILLED, OrderStatus.CLOSED), OrderStatus.CLOSED
        )

    def test_terminal_states_reject_any_transition(self):
        for terminal in (OrderStatus.REJECTED, OrderStatus.TIMEOUT, OrderStatus.CLOSED):
            with self.subTest(state=terminal), self.assertRaises(DomainError):
                transition(terminal, OrderStatus.FILLED)

    def test_new_cannot_close_directly(self):
        with self.assertRaises(DomainError):
            transition(OrderStatus.NEW, OrderStatus.CLOSED)


class SubmitTest(unittest.TestCase):
    def test_fill_applies_slippage_and_entry_fee(self):
        db, token, signal = setup_db()
        order = execution(db).submit(command(token, signal))
        self.assertEqual(order.status, OrderStatus.FILLED)
        self.assertEqual(order.fill_price, D("2") * D("1.005"))
        self.assertEqual(order.entry_fee, D("0.001") * D("2.01") * D("10"))
        ledger = db.query_one(
            "SELECT amount_quote FROM ledger_entries WHERE kind = 'ENTRY_FEE'"
        )
        self.assertEqual(D(ledger["amount_quote"]), -order.entry_fee)

    def test_reject_fault_has_no_fill_and_no_fee(self):
        db, token, signal = setup_db()
        order = execution(db, faults=FaultPlan(reject=True)).submit(
            command(token, signal)
        )
        self.assertEqual(order.status, OrderStatus.REJECTED)
        self.assertIsNone(order.fill_price)
        self.assertEqual(order.filled_units, D(0))
        self.assertEqual(
            db.query_one("SELECT COUNT(*) AS n FROM ledger_entries")["n"], 0
        )

    def test_timeout_fault_is_terminal_without_fill(self):
        db, token, signal = setup_db()
        order = execution(db, faults=FaultPlan(timeout=True)).submit(
            command(token, signal)
        )
        self.assertEqual(order.status, OrderStatus.TIMEOUT)
        self.assertEqual(execution(db).open_orders(), [])

    def test_partial_fill_fills_fraction_and_charges_fee_on_filled_part(self):
        db, token, signal = setup_db()
        order = execution(db, faults=FaultPlan(partial_ratio=D("0.4"))).submit(
            command(token, signal)
        )
        self.assertEqual(order.status, OrderStatus.PARTIALLY_FILLED)
        self.assertEqual(order.filled_units, D("4"))
        self.assertEqual(order.requested_units, D("10"))
        self.assertEqual(order.entry_fee, D("0.001") * D("2.01") * D("4"))

    def test_partial_ratio_bounds(self):
        db, _, _ = setup_db()
        for ratio in ("0", "1", "1.5"):
            with self.subTest(ratio=ratio), self.assertRaises(DomainError):
                execution(db, faults=FaultPlan(partial_ratio=D(ratio)))

    def test_duplicate_submit_returns_original_order(self):
        db, token, signal = setup_db()
        ex = execution(db)
        first = ex.submit(command(token, signal))
        second = ex.submit(command(token, signal, size="999"))
        self.assertEqual(first.id, second.id)
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM orders")["n"], 1)

    def test_non_positive_size_rejected(self):
        db, token, signal = setup_db()
        with self.assertRaises(DomainError):
            execution(db).submit(command(token, signal, size="0"))

    def test_live_or_non_dry_run_construction_refused(self):
        db, _, _ = setup_db()
        with self.assertRaises(ConfigurationError):
            execution(db, paper=False)
        with self.assertRaises(ConfigurationError):
            execution(db, dry=False)


class ClosureAndLedgerTest(unittest.TestCase):
    def open_order(self):
        db, token, signal = setup_db()
        ex = execution(db)
        order = ex.submit(command(token, signal))
        return db, ex, order

    def test_take_profit_closes_with_positive_pnl_net_of_fees(self):
        db, ex, order = self.open_order()
        closed = ex.on_price(order.id, D("2.4"))
        self.assertEqual(closed.status, OrderStatus.CLOSED)
        exit_price = D("2.3") * D("0.995")
        gross = (exit_price - order.fill_price) * D("10")
        exit_fee = D("0.001") * exit_price * D("10")
        self.assertEqual(closed.realized_pnl, gross - order.entry_fee - exit_fee)
        self.assertGreater(closed.realized_pnl, 0)

    def test_stop_loss_closes_with_negative_pnl(self):
        db, ex, order = self.open_order()
        closed = ex.on_price(order.id, D("1.7"))
        self.assertLess(closed.realized_pnl, 0)
        self.assertEqual(closed.exit_price, D("1.8") * D("0.995"))

    def test_price_between_levels_does_nothing(self):
        db, ex, order = self.open_order()
        self.assertIsNone(ex.on_price(order.id, D("2.1")))
        self.assertEqual(ex.get(order.id).status, OrderStatus.FILLED)

    def test_closed_order_cannot_close_twice(self):
        db, ex, order = self.open_order()
        ex.on_price(order.id, D("2.4"))
        self.assertIsNone(ex.on_price(order.id, D("1")))

    def test_ledger_reconciles_after_close(self):
        db, ex, order = self.open_order()
        ex.on_price(order.id, D("1.5"))
        self.assertEqual(ex.reconcile(), [])

    def test_ledger_reconciles_with_open_orders(self):
        db, ex, _ = self.open_order()
        self.assertEqual(ex.reconcile(), [])

    def test_reconcile_detects_tampered_ledger(self):
        db, ex, order = self.open_order()
        ex.on_price(order.id, D("2.4"))
        with db.transaction() as conn:
            conn.execute(
                "UPDATE ledger_entries SET amount_quote = '999' WHERE kind = 'REALIZED_PNL'"
            )
        self.assertTrue(ex.reconcile())

    def test_fee_rate_zero_gives_pure_price_pnl(self):
        db, token, signal = setup_db()
        ex = execution(db, fee="0", slip="0")
        order = ex.submit(command(token, signal))
        closed = ex.on_price(order.id, D("2.3"))
        self.assertEqual(closed.realized_pnl, (D("2.3") - D("2")) * D("10"))


class RestartRecoveryTest(unittest.TestCase):
    def test_open_position_survives_restart_and_can_still_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "paper.db")
            db, token, signal = setup_db(path)
            order = execution(db).submit(command(token, signal))
            db.close()
            db2 = Database(path)
            db2.migrate()
            ex2 = execution(db2)
            open_now = ex2.open_orders()
            self.assertEqual([o.id for o in open_now], [order.id])
            closed = ex2.on_price(order.id, D("2.5"))
            self.assertEqual(closed.status, OrderStatus.CLOSED)
            self.assertEqual(ex2.reconcile(), [])
            db2.close()


if __name__ == "__main__":
    unittest.main()
