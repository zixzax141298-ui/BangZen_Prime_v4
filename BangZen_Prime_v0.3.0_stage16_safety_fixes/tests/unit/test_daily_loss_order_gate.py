import unittest
from datetime import timedelta
from decimal import Decimal as D

from bangzen_prime.core.errors import DomainError
from bangzen_prime.execution.paper_trading import PaperPortfolio, PaperTradingUseCase
from bangzen_prime.risk.daily_loss import (
    DAILY_LOSS_LIMIT,
    DAILY_LOSS_UNAVAILABLE,
    daily_loss_reason,
)
from bangzen_prime.risk.risk import size_position
from bangzen_prime.risk.risk_engine import ExposureReservations
from bangzen_prime.risk.risk_engine import RiskDecision
from bangzen_prime.storage.repositories import UnitOfWork
from tests.integration.test_execution import execution, setup_db
from tests.support import START


class _PassEngine:
    limits = type("L", (), {"max_portfolio_age": timedelta(seconds=60)})()

    def evaluate(self, request, snapshot, now, token_program_evidence=None):
        sizing = size_position(
            equity_quote=D(1000), risk_pct=D(1), levels=request.levels,
            fee_rate=D("0.001"), slippage_rate=request.slippage_pct / D(100),
        )
        return RiskDecision(True, (), sizing)


def _use_case(db, signal_ctx, **extra):
    return PaperTradingUseCase(
        db=db, uow=UnitOfWork(db), engine=_PassEngine(), execution=execution(db),
        portfolio=PaperPortfolio(db, D(1000)),
        reservations=ExposureReservations(D(500)),
        clock=lambda: START, expected_slippage_pct=D("0.5"),
        price_lookup=lambda _mint: D("2.1"),
        spread_lookup=lambda _mint: D("0.2"),
        **extra,
    )


def _order_count(db) -> int:
    return db.query_one("SELECT COUNT(*) AS n FROM orders")["n"]


class DailyLossReasonTest(unittest.TestCase):
    def test_unknown_loss_is_refused_not_treated_as_zero(self):
        self.assertEqual(daily_loss_reason(None, D("1.0")), DAILY_LOSS_UNAVAILABLE)
        self.assertEqual(daily_loss_reason(D("NaN"), D("1.0")), DAILY_LOSS_UNAVAILABLE)

    def test_threshold_is_inclusive_and_below_passes(self):
        self.assertIsNone(daily_loss_reason(D("0.99"), D("1.0")))
        self.assertEqual(daily_loss_reason(D("1.0"), D("1.0")), DAILY_LOSS_LIMIT)
        self.assertEqual(daily_loss_reason(D("3"), D("1.0")), DAILY_LOSS_LIMIT)

    def test_zero_loss_passes(self):
        self.assertIsNone(daily_loss_reason(D(0), D("1.0")))

    def test_invalid_inputs_raise(self):
        with self.assertRaises(DomainError):
            daily_loss_reason(D("-1"), D("1.0"))
        with self.assertRaises(DomainError):
            daily_loss_reason(D(0), D(0))
        with self.assertRaises(DomainError):
            daily_loss_reason(D(0), D(101))
        with self.assertRaises(DomainError):
            daily_loss_reason(D(0), 1.0)  # type: ignore[arg-type]


class PaperOpenDailyLossGateTest(unittest.TestCase):
    def test_order_refused_when_daily_loss_limit_reached(self):
        db, _token, signal = setup_db()
        uc = _use_case(db, signal, daily_loss_provider=lambda now: D("1.5"))
        outcome = uc.open_from_signal(signal.id)
        self.assertIsNone(outcome.order)
        self.assertEqual(outcome.decision.reasons, (DAILY_LOSS_LIMIT,))
        self.assertEqual(_order_count(db), 0)

    def test_order_allowed_when_loss_is_below_limit(self):
        db, _token, signal = setup_db()
        uc = _use_case(db, signal, daily_loss_provider=lambda now: D("0.2"))
        outcome = uc.open_from_signal(signal.id)
        self.assertIsNotNone(outcome.order)
        self.assertEqual(_order_count(db), 1)

    def test_unreadable_loss_refuses_order(self):
        db, _token, signal = setup_db()
        uc = _use_case(db, signal, daily_loss_provider=lambda now: None)
        outcome = uc.open_from_signal(signal.id)
        self.assertIsNone(outcome.order)
        self.assertEqual(outcome.decision.reasons, (DAILY_LOSS_UNAVAILABLE,))
        self.assertEqual(_order_count(db), 0)

    def test_provider_exception_refuses_order(self):
        def broken(now):
            raise RuntimeError("db locked")

        db, _token, signal = setup_db()
        uc = _use_case(db, signal, daily_loss_provider=broken)
        outcome = uc.open_from_signal(signal.id)
        self.assertEqual(outcome.decision.reasons, (DAILY_LOSS_UNAVAILABLE,))
        self.assertEqual(_order_count(db), 0)

    def test_without_provider_behaviour_is_unchanged(self):
        db, _token, signal = setup_db()
        outcome = _use_case(db, signal).open_from_signal(signal.id)
        self.assertIsNotNone(outcome.order)

    def test_bad_limit_fails_at_construction(self):
        db, _token, signal = setup_db()
        with self.assertRaises(DomainError):
            _use_case(db, signal, daily_loss_provider=lambda now: D(0),
                      daily_loss_limit_pct=D(0))


class DailyLossProviderAdapterTest(unittest.TestCase):
    def test_adapter_reads_todays_loss_from_database(self):
        from bangzen_prime.risk.risk_state import DbRiskStateReader, daily_loss_provider

        db, _token, _signal = setup_db()
        provide = daily_loss_provider(DbRiskStateReader(db, D(1000)))
        self.assertEqual(provide(START), D(0))

    def test_adapter_returns_none_when_reader_fails(self):
        from bangzen_prime.risk.risk_state import daily_loss_provider

        class Broken:
            def read(self, now):
                raise RuntimeError("disk gone")

        self.assertIsNone(daily_loss_provider(Broken())(START))


class PaperEntrypointWiringTest(unittest.TestCase):
    """Guard: the operator paper entrypoints must keep the daily-loss re-check wired."""

    def test_demo_and_soak_pass_daily_loss_provider(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[2] / "bangzen_prime" / "core" / "interfaces"
        for name in ("demo.py", "soak.py"):
            source = (root / name).read_text(encoding="utf-8")
            self.assertIn("daily_loss_provider=daily_loss_provider(", source, name)
            self.assertIn("daily_loss_limit_pct=RiskGovernor().daily_loss_limit_pct", source, name)


if __name__ == "__main__":
    unittest.main()
