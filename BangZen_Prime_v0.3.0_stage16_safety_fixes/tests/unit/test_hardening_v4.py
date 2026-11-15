"""Regression tests for the v4 hardening pass.

Each test pins a behaviour that was wrong before:
  - sizing ignored slippage (realised loss exceeded the risk budget)
  - stop-loss gaps were booked at the stop level instead of the real price
  - equity ignored open-position losses (no mark to market)
  - RiskGovernor received hardcoded zeros, so its limits never fired
  - paper fills used the signal price and a fabricated price of 1
  - notional ignored token decimals
  - monitor spent budget on duplicates and recorded fake phase transitions
  - Telegram length was counted in code points, not UTF-16 units
  - env inline comments leaked into values; MAX_OPEN_POSITIONS=0 was accepted
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal

from bangzen_prime.core.config import Settings, parse_env_file
from bangzen_prime.core.errors import ConfigurationError
from bangzen_prime.core.use_cases import RejectReason, ScanResult
from bangzen_prime.execution.paper_trading import PaperPortfolio
from bangzen_prime.risk.risk import size_position
from bangzen_prime.risk.risk_engine import RiskEngine
from bangzen_prime.risk.risk_state import DbRiskStateReader
from bangzen_prime.scoring.signals import PriceLevels
from bangzen_prime.storage.database import parse_iso
from tests.integration.test_execution import command, execution, setup_db
from tests.support import START, TOKEN_MINT
from tests.unit.test_monitor import MINTS, Clock, FakeScan, monitor_with
from tests.unit.test_risk_engine import limits, portfolio, request

D = Decimal


class SizingSlippageTest(unittest.TestCase):
    def test_realised_loss_at_stop_stays_within_budget_with_slippage(self):
        levels = PriceLevels(D(1), D("0.9"), D("1.3"))
        fee = D("0.001")
        slip = D("0.005")
        s = size_position(
            equity_quote=D(1000),
            risk_pct=D(1),
            levels=levels,
            fee_rate=fee,
            slippage_rate=slip,
        )
        # Replay the simulator's own arithmetic for a stop-out at the stop level.
        fill = levels.entry * (1 + slip)
        exit_px = levels.stop_loss * (1 - slip)
        realised = (
            (fill - exit_px) * s.size_units + fee * fill * s.size_units + fee * exit_px * s.size_units
        )
        self.assertLessEqual(realised, D(10) + D("1E-12"))
        self.assertAlmostEqual(realised, D(10), places=12)

    def test_without_slippage_result_is_unchanged(self):
        levels = PriceLevels(D(2), D("1.8"), D("2.3"))
        base = size_position(equity_quote=D(1000), risk_pct=D(1), levels=levels, fee_rate=D("0.001"))
        zero = size_position(
            equity_quote=D(1000), risk_pct=D(1), levels=levels, fee_rate=D("0.001"), slippage_rate=D(0)
        )
        self.assertEqual(base.size_units, zero.size_units)

    def test_slippage_at_or_above_one_rejected(self):
        levels = PriceLevels(D(2), D("1.8"), D("2.3"))
        from bangzen_prime.core.errors import DomainError

        with self.assertRaises(DomainError):
            size_position(
                equity_quote=D(1000), risk_pct=D(1), levels=levels,
                fee_rate=D(0), slippage_rate=D(1),
            )


class SpreadFailClosedTest(unittest.TestCase):
    def test_unknown_spread_is_rejected_not_treated_as_zero(self):
        decision = RiskEngine(limits()).evaluate(request(spread_pct=None), portfolio(), START)
        self.assertFalse(decision.approved)
        self.assertIn("SPREAD_UNAVAILABLE", decision.reasons)

    def test_known_tight_spread_still_passes_spread_check(self):
        decision = RiskEngine(limits()).evaluate(request(spread_pct=D("0.1")), portfolio(), START)
        self.assertNotIn("SPREAD_UNAVAILABLE", decision.reasons)
        self.assertNotIn("SPREAD_TOO_WIDE", decision.reasons)


class SlippageConsistencyTest(unittest.TestCase):
    def test_paper_engine_refuses_mismatched_slippage(self):
        from bangzen_prime.execution.paper_trading import PaperTradingUseCase

        db, _, _ = setup_db()
        ex = execution(db, slip="0.005")  # 0.5% -> 0.5 percent
        with self.assertRaises(ConfigurationError):
            PaperTradingUseCase(
                db=db, uow=None, engine=None, execution=ex,
                portfolio=None, reservations=None, clock=lambda: START,
                expected_slippage_pct=D("1.0"),
            )

    def test_executor_exposes_slippage_rate(self):
        db, _, _ = setup_db()
        self.assertEqual(execution(db, slip="0.005").slippage_rate, D("0.005"))


class MarkToMarketTest(unittest.TestCase):
    def open_position(self):
        db, token, signal = setup_db()
        ex = execution(db)
        order = ex.submit(command(token, signal))
        return db, ex, order

    def test_unrealised_loss_reduces_equity_when_mark_is_known(self):
        db, ex, order = self.open_position()
        at_fill = PaperPortfolio(db, D(1000)).snapshot(
            START, marks={TOKEN_MINT: order.fill_price}
        )
        marked = PaperPortfolio(db, D(1000)).snapshot(START, marks={TOKEN_MINT: D("1.9")})
        self.assertLess(marked.equity_quote, at_fill.equity_quote)

    def test_missing_mark_values_position_at_stop_not_entry(self):
        db, ex, order = self.open_position()
        unmarked = PaperPortfolio(db, D(1000)).snapshot(START)
        at_stop = PaperPortfolio(db, D(1000)).snapshot(START, marks={TOKEN_MINT: order.stop_loss})
        self.assertEqual(unmarked.equity_quote, at_stop.equity_quote)
        self.assertLess(unmarked.equity_quote, D(1000))

    def test_drawdown_sees_open_loss(self):
        db, ex, order = self.open_position()
        snap = PaperPortfolio(db, D(1000)).snapshot(START, marks={TOKEN_MINT: D("1.85")})
        self.assertGreater(snap.drawdown_pct, D(0))


class RiskGovernorLiveStateTest(unittest.TestCase):
    def test_empty_book_reports_zero_risk(self):
        db = setup_db()[0]
        # setup_db creates one accepted signal; the book itself has no orders.
        signal_row = db.query_one("SELECT created_at FROM signals LIMIT 1")
        state = DbRiskStateReader(db, D(1000)).read(parse_iso(signal_row["created_at"]))
        self.assertEqual(state.open_positions, 0)
        self.assertEqual(state.portfolio_risk_pct, D(0))
        self.assertEqual(state.daily_loss_pct, D(0))

    def test_open_order_counts_as_position_and_risk(self):
        db, token, signal = setup_db()
        execution(db).submit(command(token, signal))
        now = parse_iso(db.query_one("SELECT created_at FROM signals LIMIT 1")["created_at"])
        state = DbRiskStateReader(db, D(1000)).read(now)
        self.assertEqual(state.open_positions, 1)
        self.assertGreater(state.portfolio_risk_pct, D(0))

    def test_todays_realised_loss_is_reported_and_blocks_governor(self):
        from bangzen_prime.core.use_cases import RiskGovernor

        # Small account so a ~10 quote stop-out is a 5% daily loss, above the 1% limit.
        db, token, signal = setup_db()
        ex = execution(db)
        order = ex.submit(command(token, signal))
        ex.on_price(order.id, D("1.7"))  # stop-out: realised loss
        now = parse_iso(db.query_one("SELECT created_at FROM signals LIMIT 1")["created_at"])
        state = DbRiskStateReader(db, D(200)).read(now)
        self.assertGreater(state.daily_loss_pct, D("1.0"))
        allowed, reason = RiskGovernor().can_accept_new_signal(
            open_positions=state.open_positions,
            signals_today=state.signals_today,
            portfolio_risk_pct=state.portfolio_risk_pct,
            daily_loss_pct=state.daily_loss_pct,
        )
        self.assertFalse(allowed)
        self.assertIsNotNone(reason)

    def test_starting_equity_must_be_positive(self):
        db = setup_db()[0]
        with self.assertRaises(ValueError):
            DbRiskStateReader(db, D(0))


class MonitorBudgetAndPhaseTest(unittest.TestCase):
    def test_duplicate_scan_does_not_spend_budget(self):
        class DupScan(FakeScan):
            def is_recent(self, mint):
                return True

        scan = DupScan({})
        m = monitor_with(scan, Clock(), per_minute=5, mints=MINTS)
        before = m.budget.remaining("dexscreener")
        report = m.run_cycle()
        self.assertEqual(report.scanned, 0)
        self.assertEqual(m.budget.remaining("dexscreener"), before)
        self.assertEqual(scan.calls, [])

    def test_unobserved_phase_is_not_recorded_as_transition(self):
        class NoPhaseScan(FakeScan):
            def execute(self, chain, mints):
                self.calls.append(mints[0])
                return [ScanResult(mints[0], "WATCH", (RejectReason.EMPTY_MARKET.value,), None, None, None)]

        scan = NoPhaseScan({})
        m = monitor_with(scan, Clock(), per_minute=10, mints=MINTS[:1])
        m.run_cycle()
        m.run_cycle()
        self.assertEqual(m._last_phase, {})

    def test_watchlist_rotates_so_budget_does_not_starve_the_tail(self):
        m = monitor_with(FakeScan({}), Clock(), per_minute=10, mints=MINTS)
        m._cycle = 1
        first = m._rotated()[0]
        m._cycle = 2
        second = m._rotated()[0]
        self.assertNotEqual(first, second)
        self.assertEqual(sorted(m._rotated()), sorted(MINTS))

    def test_spend_returns_false_instead_of_raising(self):
        m = monitor_with(FakeScan({}), Clock(), per_minute=1, mints=MINTS)
        self.assertTrue(m._spend())
        self.assertFalse(m._spend())



class SettingsHardeningTest(unittest.TestCase):
    def test_inline_comment_is_not_part_of_unquoted_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".env")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("BANGZEN_LOG_LEVEL=WARNING # verbose off\n")
            self.assertEqual(parse_env_file(path)["BANGZEN_LOG_LEVEL"], "WARNING")

    def test_hash_inside_quoted_value_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, ".env")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('BANGZEN_DB_PATH="data #1.db"\n')
            self.assertEqual(parse_env_file(path)["BANGZEN_DB_PATH"], "data #1.db")

    def test_zero_open_positions_rejected_at_config_time(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_MAX_OPEN_POSITIONS": "0"})


if __name__ == "__main__":
    unittest.main()


class PaperExecutionPricingTest(unittest.IsolatedAsyncioTestCase):
    def _uc(self, lookup):
        from bangzen_prime.core.operating_mode import OperatingMode
        from bangzen_prime.core.state import ModeController
        from bangzen_prime.execution.execution_use_case import (
            ExecutionPolicy,
            ExecutionUseCase,
        )
        from tests.unit.test_execution_use_case import NOW, FakeNotifier, FakePaperFill

        return ExecutionUseCase(
            mode_controller=ModeController(OperatingMode.EXECUTION_ONLY),
            policy=ExecutionPolicy(live_enabled=False, paper_trading=True, dry_run=True),
            notifier=FakeNotifier(),
            paper_fill=FakePaperFill(),
            market_price_lookup=lookup,
            clock=lambda: NOW,
        )

    async def test_no_price_lookup_rejects_instead_of_fabricating_price_one(self):
        from tests.unit.test_execution_use_case import plan

        result = await self._uc(None).execute(plan())
        self.assertNotEqual(result.status.value, "PAPER_FILLED")
        self.assertIn("MARKET_PRICE_UNAVAILABLE", result.reason_codes)

    async def test_unknown_decimals_rejects(self):
        from tests.unit.test_execution_use_case import _coro, plan

        result = await self._uc(lambda _m: _coro(D("2.5"))).execute(plan(input_decimals=None))
        self.assertIn("DECIMALS_UNKNOWN", result.reason_codes)

    async def test_fee_uses_whole_token_notional_not_atomic_units(self):
        from tests.unit.test_execution_use_case import _coro, plan

        # 1_000_000 atomic USDC (6 decimals) = 1 whole token. Notional = 1 * 2.5 = 2.5.
        result = await self._uc(lambda _m: _coro(D("2.5"))).execute(plan())
        self.assertEqual(result.status.value, "PAPER_FILLED")
        self.assertLess(result.paper_fee, D("1"))
        self.assertGreater(result.paper_fee, D(0))

    def test_plan_rejects_invalid_decimals(self):
        from bangzen_prime.core.errors import DomainError
        from tests.unit.test_execution_use_case import plan

        with self.assertRaises(DomainError):
            plan(input_decimals=99)


class PaperOpenPathTest(unittest.TestCase):
    """Orchestration of open_from_signal: live price, fail-closed gates, real sizing.

    The risk engine is replaced by a pass-through that still performs real sizing, because the
    full engine needs token-program evidence that is out of scope here. What is under test is
    that the order is priced at the current market, not the signal price.
    """

    class PassEngine:
        limits = type("L", (), {"max_portfolio_age": timedelta(seconds=60)})()

        def evaluate(self, request, snapshot, now, token_program_evidence=None):
            from bangzen_prime.risk.risk import size_position
            from bangzen_prime.risk.risk_engine import RiskDecision

            sizing = size_position(
                equity_quote=D(1000), risk_pct=D(1), levels=request.levels,
                fee_rate=D("0.001"), slippage_rate=request.slippage_pct / D(100),
            )
            return RiskDecision(True, (), sizing)

    def build(self, price, spread=D("0.2")):
        from bangzen_prime.execution.paper_trading import (
            PaperPortfolio,
            PaperTradingUseCase,
        )
        from bangzen_prime.risk.risk_engine import ExposureReservations
        from bangzen_prime.storage.repositories import UnitOfWork

        db, token, signal = setup_db()
        ex = execution(db)
        uc = PaperTradingUseCase(
            db=db, uow=UnitOfWork(db), engine=self.PassEngine(), execution=ex,
            portfolio=PaperPortfolio(db, D(1000)),
            reservations=ExposureReservations(D(500)),
            clock=lambda: START, expected_slippage_pct=D("0.5"),
            price_lookup=lambda _mint: price,
            spread_lookup=lambda _mint: spread,
        )
        return db, signal, uc

    def test_order_is_priced_at_current_market_not_signal_price(self):
        db, signal, uc = self.build(price=D("2.1"))
        outcome = uc.open_from_signal(signal.id)
        self.assertIsNotNone(outcome.order)
        self.assertEqual(outcome.order.entry_price, D("2.1"))
        self.assertEqual(outcome.order.fill_price, D("2.1") * (1 + D("0.005")))

    def test_missing_market_price_rejects(self):
        db, signal, uc = self.build(price=None)
        outcome = uc.open_from_signal(signal.id)
        self.assertIsNone(outcome.order)
        self.assertIn("MARKET_PRICE_UNAVAILABLE", outcome.decision.reasons)

    def test_price_that_breaks_stop_target_geometry_rejects(self):
        db, signal, uc = self.build(price=D("1.7"))  # below the 1.8 stop
        outcome = uc.open_from_signal(signal.id)
        self.assertIsNone(outcome.order)
        self.assertIn("LEVELS_INVALIDATED_AT_MARKET", outcome.decision.reasons)

    def test_rejected_attempts_are_audited(self):
        db, signal, uc = self.build(price=None)
        uc.open_from_signal(signal.id)
        rows = db.query_all("SELECT payload FROM audit_log WHERE event_type = 'RiskDecision'")
        self.assertTrue(rows)


class SettlementTest(unittest.TestCase):
    PassEngine = PaperOpenPathTest.PassEngine
    build = PaperOpenPathTest.build

    def test_settles_position_when_market_hits_stop(self):
        db, signal, uc = self.build(price=D("2.1"))
        opened = uc.open_from_signal(signal.id).order
        self.assertIsNotNone(opened)
        uc._price_lookup = lambda _m: D("1.7")  # gap through the 1.8 stop
        closed = uc.settle_open_positions()
        self.assertEqual(len(closed), 1)
        self.assertLess(closed[0].realized_pnl, 0)

    def test_unknown_price_keeps_position_open(self):
        db, signal, uc = self.build(price=D("2.1"))
        uc.open_from_signal(signal.id)
        uc._price_lookup = lambda _m: None
        self.assertEqual(uc.settle_open_positions(), [])
        self.assertEqual(len(uc._execution.open_orders()), 1)


class VolumeFloorTest(unittest.TestCase):
    def test_default_floor_is_not_the_old_any_volume_check(self):
        from bangzen_prime.core.use_cases import SignalPolicy

        policy = SignalPolicy(min_liquidity_usd=D(10000), max_risk_score=D(60), max_data_age_seconds=120)
        self.assertGreaterEqual(policy.min_volume_24h_usd, D(1000))

    def test_env_sets_volume_floor(self):
        s = Settings.from_env({"BANGZEN_MIN_VOLUME_24H_USD": "12500"})
        self.assertEqual(s.min_volume_24h_usd, D("12500"))

    def test_negative_volume_floor_rejected(self):
        with self.assertRaises(Exception):
            Settings.from_env({"BANGZEN_MIN_VOLUME_24H_USD": "-1"})
