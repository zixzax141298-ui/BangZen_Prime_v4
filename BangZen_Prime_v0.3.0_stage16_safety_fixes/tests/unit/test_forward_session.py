import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path

from bangzen_prime.core.errors import DomainError
from bangzen_prime.execution.forward_session import (
    ForwardPaperSession,
    paper_config_hash,
)
from bangzen_prime.execution.paper_trading import PaperPortfolio, PaperTradingUseCase
from bangzen_prime.research.forward_paper import ForwardPaperLedger
from bangzen_prime.risk.daily_loss import DAILY_LOSS_LIMIT
from bangzen_prime.risk.risk import size_position
from bangzen_prime.risk.risk_engine import ExposureReservations, RiskDecision, RiskLimits
from bangzen_prime.storage.database import utc_iso
from bangzen_prime.storage.repositories import UnitOfWork
from tests.integration.test_execution import TOKEN_MINT, execution, setup_db
from tests.support import START

CFG = paper_config_hash(
    risk_limits=RiskLimits(
        max_risk_per_trade_pct=D(1), max_open_positions=3, max_exposure_quote=D(500),
        max_drawdown_pct=D(50), min_liquidity_usd=D(0), max_spread_pct=D(5),
        max_slippage_pct=D(5), fee_rate=D("0.001"),
    ),
    fee_rate=D("0.001"),
    slippage_rate=D("0.005"),
    daily_loss_limit_pct=D("1.0"),
)


class _PassEngine:
    limits = type("L", (), {"max_portfolio_age": timedelta(seconds=60)})()

    def evaluate(self, request, snapshot, now, token_program_evidence=None):
        sizing = size_position(
            equity_quote=D(1000), risk_pct=D(1), levels=request.levels,
            fee_rate=D("0.001"), slippage_rate=request.slippage_pct / D(100),
        )
        return RiskDecision(True, (), sizing)


class ForwardSessionTest(unittest.TestCase):
    def setUp(self):
        self.db, self.token, self.signal = setup_db()
        self.price = {"value": D("2.1")}
        self.paper = PaperTradingUseCase(
            db=self.db, uow=UnitOfWork(self.db), engine=_PassEngine(),
            execution=execution(self.db), portfolio=PaperPortfolio(self.db, D(1000)),
            reservations=ExposureReservations(D(500)), clock=lambda: START,
            expected_slippage_pct=D("0.5"),
            price_lookup=lambda mint: self.price["value"] if mint == TOKEN_MINT else None,
            spread_lookup=lambda _mint: D("0.2"),
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "forward.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def _session(self, path=None):
        return ForwardPaperSession(paper=self.paper, db=self.db,
                                   ledger=ForwardPaperLedger(CFG, D(1000)), ledger_path=path)

    def test_open_then_settle_records_trade_with_lifecycle_phase_from_token(self):
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO token_lifecycle (chain, mint, phase, first_seen_at, last_seen_at,"
                " last_observed_at, reason, evidence_json) VALUES ('solana', ?, 'LAUNCH', ?, ?, ?, 'T', '{}')",
                (TOKEN_MINT, utc_iso(START), utc_iso(START), utc_iso(START)),
            )
        session = self._session(self.path)
        first = session.run_once([self.signal.id])
        self.assertEqual(len(first.opened), 1)
        self.assertEqual(first.closed, 0)
        self.assertEqual(len(session.ledger.entries), 0)

        self.price["value"] = D(1000)  # above take-profit: settlement closes the order
        second = session.run_once([])
        self.assertEqual(second.closed, 1)
        self.assertEqual(second.recorded, 1)
        entry = session.ledger.entries[0]
        self.assertEqual(entry.trade.lifecycle_phase, "LAUNCH")
        self.assertTrue(session.ledger.verify_chain())

    def test_phase_is_unknown_when_token_has_no_lifecycle_row(self):
        session = self._session()
        session.run_once([self.signal.id])
        self.price["value"] = D(1000)
        session.run_once([])
        self.assertEqual(session.ledger.entries[0].trade.lifecycle_phase, "UNKNOWN")

    def test_phase_survives_restart_because_it_is_stored_in_the_database(self):
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO token_lifecycle (chain, mint, phase, first_seen_at, last_seen_at,"
                " last_observed_at, reason, evidence_json) VALUES ('solana', ?, 'EXPANSION', ?, ?, ?, 'T', '{}')",
                (TOKEN_MINT, utc_iso(START), utc_iso(START), utc_iso(START)),
            )
        before_restart = self._session(self.path)
        before_restart.run_once([self.signal.id])
        # Simulated restart: new session object, new empty ledger, same database.
        after_restart = self._session(self.path)
        self.price["value"] = D(1000)
        after_restart.run_once([])
        self.assertEqual(after_restart.ledger.entries[0].trade.lifecycle_phase, "EXPANSION")

    def test_rejected_signal_is_reported_with_reason_and_opens_nothing(self):
        paper = PaperTradingUseCase(
            db=self.db, uow=UnitOfWork(self.db), engine=_PassEngine(),
            execution=execution(self.db), portfolio=PaperPortfolio(self.db, D(1000)),
            reservations=ExposureReservations(D(500)), clock=lambda: START,
            expected_slippage_pct=D("0.5"),
            price_lookup=lambda _mint: D("2.1"), spread_lookup=lambda _mint: D("0.2"),
            daily_loss_provider=lambda now: D("5"),
        )
        session = ForwardPaperSession(paper=paper, db=self.db, ledger=ForwardPaperLedger(CFG, D(1000)))
        cycle = session.run_once([self.signal.id])
        self.assertEqual(cycle.opened, ())
        self.assertEqual(cycle.rejected[0][1], (DAILY_LOSS_LIMIT,))

    def test_ledger_is_saved_and_reloaded_with_same_frozen_config(self):
        session = self._session(self.path)
        session.run_once([self.signal.id])
        self.price["value"] = D(1000)
        session.run_once([])
        reopened = ForwardPaperSession.open(
            paper=self.paper, db=self.db, ledger_path=self.path,
            config_hash_value=CFG, initial_equity=D(1000),
        )
        self.assertEqual(len(reopened.ledger.entries), 1)
        self.assertTrue(reopened.ledger.verify_chain())

    def test_existing_ledger_with_different_config_is_refused(self):
        self._session(self.path).run_once([])
        other = paper_config_hash(
            risk_limits=RiskLimits(
                max_risk_per_trade_pct=D(2), max_open_positions=3, max_exposure_quote=D(500),
                max_drawdown_pct=D(50), min_liquidity_usd=D(0), max_spread_pct=D(5),
                max_slippage_pct=D(5), fee_rate=D("0.001"),
            ),
            fee_rate=D("0.001"), slippage_rate=D("0.005"), daily_loss_limit_pct=D("1.0"),
        )
        with self.assertRaises(DomainError):
            ForwardPaperSession.open(paper=self.paper, db=self.db, ledger_path=self.path,
                                     config_hash_value=other, initial_equity=D(1000))


class PaperConfigHashTest(unittest.TestCase):
    def test_hash_is_stable_and_changes_with_fee(self):
        limits = RiskLimits(
            max_risk_per_trade_pct=D(1), max_open_positions=3, max_exposure_quote=D(500),
            max_drawdown_pct=D(50), min_liquidity_usd=D(0), max_spread_pct=D(5),
            max_slippage_pct=D(5), fee_rate=D("0.001"),
        )
        a = paper_config_hash(risk_limits=limits, fee_rate=D("0.001"), slippage_rate=D("0.005"),
                              daily_loss_limit_pct=D("1.0"))
        b = paper_config_hash(risk_limits=limits, fee_rate=D("0.001"), slippage_rate=D("0.005"),
                              daily_loss_limit_pct=D("1.0"))
        c = paper_config_hash(risk_limits=limits, fee_rate=D("0.002"), slippage_rate=D("0.005"),
                              daily_loss_limit_pct=D("1.0"))
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(len(a), 64)


if __name__ == "__main__":
    unittest.main()
