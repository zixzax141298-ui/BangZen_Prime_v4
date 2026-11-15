import unittest
import uuid
from decimal import Decimal

from bangzen_prime.core.interfaces.demo import SIMULATED_SPREAD_PCT, latest_sampled_price
from bangzen_prime.core.config import Settings
from bangzen_prime.execution.orders import OrderStatus
from bangzen_prime.execution.paper_trading import PaperPortfolio, PaperTradingUseCase
from bangzen_prime.execution.simulated import SimulatedExecution
from bangzen_prime.risk.risk_engine import (
    ExposureReservations,
    RiskEngine,
    RiskLimits,
)
from bangzen_prime.security.token_program_evidence import TokenProgramEvidenceUseCase
from tests.e2e.test_scan_flow import Token2022Reader, World, build
from tests.support import TOKEN_MINT

D = Decimal


def make_paper(container, *, starting=D("1000"), max_positions=3, exposure=D("500")):
    s = container.settings
    limits = RiskLimits(
        max_risk_per_trade_pct=s.max_risk_per_trade_pct,
        max_open_positions=max_positions,
        max_exposure_quote=exposure,
        max_drawdown_pct=s.max_drawdown_pct,
        min_liquidity_usd=s.min_liquidity_usd,
        max_spread_pct=D("1"),
        max_slippage_pct=D("1"),
        fee_rate=s.fee_rate,
    )
    execution = SimulatedExecution(
        db=container.db,
        fee_rate=s.fee_rate,
        slippage_rate=s.slippage_rate,
        clock=container.clock.now,
        paper=True,
        dry_run=True,
    )
    portfolio = PaperPortfolio(container.db, starting)
    return (
        PaperTradingUseCase(
            db=container.db,
            price_lookup=latest_sampled_price(container.db),
        spread_lookup=lambda _mint: SIMULATED_SPREAD_PCT,
            uow=container.uow,
            engine=RiskEngine(limits),
            execution=execution,
            portfolio=portfolio,
            reservations=ExposureReservations(exposure),
            clock=container.clock.now,
            expected_slippage_pct=D("0.5"),
            token_program_evidence=container.token_program_evidence,
        ),
        execution,
    )


class PaperFlowTest(unittest.TestCase):
    def accepted_signal(self):
        world = World()
        container, _, _, clock = build(
            world=world, settings=Settings(starting_equity=D("1000"))
        )
        for _ in range(20):
            clock.advance(
                91
            )  # past the 90 s dedupe cooldown so each scan adds a price sample
            container.scan.execute("solana", [TOKEN_MINT])
        row = container.db.query_one(
            "SELECT id FROM signals WHERE status = 'ACCEPTED' LIMIT 1"
        )
        self.assertIsNotNone(row, "scan must produce at least one accepted signal")
        return container, uuid.UUID(row["id"])

    def test_paper_entry_refreshes_and_vetoes_token2022_hard_risk(self):
        container, signal_id = self.accepted_signal()
        container.token_program_evidence = TokenProgramEvidenceUseCase(
            Token2022Reader(flags=("TOKEN_TRANSFERS_PAUSED",))
        )
        paper, _ = make_paper(container)
        outcome = paper.open_from_signal(signal_id)
        self.assertFalse(outcome.decision.approved)
        self.assertIn("TOKEN2022_EVIDENCE_STALE", outcome.decision.reasons)
        self.assertIsNone(outcome.order)
        self.assertEqual(
            container.db.query_one("SELECT COUNT(*) AS n FROM orders")["n"], 0
        )

    def test_accepted_signal_opens_paper_order_within_risk_limits(self):
        container, signal_id = self.accepted_signal()
        paper, _ = make_paper(container)
        outcome = paper.open_from_signal(signal_id)
        self.assertTrue(outcome.decision.approved, outcome.decision.reasons)
        self.assertEqual(outcome.order.status, OrderStatus.FILLED)
        self.assertLessEqual(outcome.decision.sizing.risk_amount_quote, D("10"))

    def test_open_is_idempotent_for_the_same_signal(self):
        container, signal_id = self.accepted_signal()
        paper, _ = make_paper(container)
        first = paper.open_from_signal(signal_id).order
        second = paper.open_from_signal(signal_id).order
        self.assertEqual(first.id, second.id)
        self.assertEqual(
            container.db.query_one("SELECT COUNT(*) AS n FROM orders")["n"], 1
        )

    def test_risk_decision_is_audited_and_audit_chain_holds(self):
        container, signal_id = self.accepted_signal()
        paper, _ = make_paper(container)
        paper.open_from_signal(signal_id)
        rows = container.db.query_all(
            "SELECT event_type FROM audit_log WHERE event_type = 'RiskDecision'"
        )
        self.assertGreaterEqual(len(rows), 1)
        from bangzen_prime.storage.outbox import AuditLog

        with container.db.transaction() as conn:
            self.assertIsNone(AuditLog(conn).verify())

    def test_unknown_signal_is_not_accepted(self):
        container, _ = self.accepted_signal()
        paper, _ = make_paper(container)
        outcome = paper.open_from_signal(uuid.uuid4())
        self.assertEqual(outcome.decision.reasons, ("SIGNAL_NOT_ACCEPTED",))
        self.assertIsNone(outcome.order)

    def test_max_positions_zero_blocks_any_signal(self):
        container, *_ = build()
        from bangzen_prime.core.errors import DomainError

        with self.assertRaises(DomainError):
            make_paper(container, max_positions=0)

    def test_portfolio_reflects_open_position_then_realised_pnl(self):
        container, signal_id = self.accepted_signal()
        paper, execution = make_paper(container)
        order = paper.open_from_signal(signal_id).order
        portfolio = PaperPortfolio(container.db, D("1000")).snapshot(
            container.clock.now()
        )
        self.assertEqual(portfolio.open_count, 1)
        self.assertLess(portfolio.equity_quote, D("1000"))
        execution.on_price(order.id, order.take_profit)
        after = PaperPortfolio(container.db, D("1000")).snapshot(container.clock.now())
        self.assertEqual(after.open_count, 0)
        self.assertGreater(after.equity_quote, portfolio.equity_quote)

    def test_stop_loss_sets_cooldown_for_next_decision(self):
        container, signal_id = self.accepted_signal()
        paper, execution = make_paper(container)
        order = paper.open_from_signal(signal_id).order
        execution.on_price(order.id, order.stop_loss)
        snap = PaperPortfolio(container.db, D("1000")).snapshot(container.clock.now())
        self.assertIsNotNone(snap.last_loss_at)
        self.assertEqual(execution.reconcile(), [])


if __name__ == "__main__":
    unittest.main()
