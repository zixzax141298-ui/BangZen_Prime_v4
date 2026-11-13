import threading
import unittest
import uuid
from datetime import timedelta
from decimal import Decimal

from bangzen_prime.application.risk_engine import (
    ExposureReservations,
    RiskEngine,
    RiskLimits,
    TradeRequest,
)
from bangzen_prime.domain.risk import OpenPosition, PortfolioSnapshot
from bangzen_prime.domain.signals import PriceLevels
from bangzen_prime.domain.token_2022_extension_evidence import (
    Token2022ExtensionEvidence,
)
from bangzen_prime.domain.token_2022_extensions import REJECTED
from bangzen_prime.domain.token_programs import TOKEN_PROGRAM_ID
from bangzen_prime.errors import DomainError
from tests.support import START, TOKEN_MINT

D = Decimal


def limits(**overrides):
    base = dict(
        max_risk_per_trade_pct=D(1),
        max_open_positions=3,
        max_exposure_quote=D(500),
        max_drawdown_pct=D(20),
        min_liquidity_usd=D(10000),
        max_spread_pct=D("1"),
        max_slippage_pct=D("1"),
        fee_rate=D("0.001"),
    )
    base.update(overrides)
    return RiskLimits(**base)


def request(**overrides):
    base = dict(
        signal_id=uuid.uuid4(),
        token_id=uuid.uuid4(),
        token_mint=TOKEN_MINT,
        levels=PriceLevels(D(2), D("1.8"), D("2.3")),
        liquidity_usd=D(50000),
        spread_pct=D(0),
        slippage_pct=D("0.5"),
        token_program=TOKEN_PROGRAM_ID,
    )
    base.update(overrides)
    return TradeRequest(**base)


def portfolio(**overrides):
    base = dict(
        equity_quote="1000", peak_equity_quote="1000", open_positions=(), as_of=START
    )
    base.update(overrides)
    return PortfolioSnapshot.create(**base)


def classic_mint_evidence(mint):
    return Token2022ExtensionEvidence(
        mint=mint,
        validation_status=REJECTED,
        observed_at=START,
        source="test",
        source_record_id="classic-mint",
        slot=1,
        token_program=TOKEN_PROGRAM_ID,
        account_data_length=82,
        reason_codes=("CLASSIC_SPL_MINT_CONFIRMED",),
    )


class RiskEngineTest(unittest.TestCase):
    def evaluate(self, lim=None, req=None, port=None, now=START):
        req = req or request()
        evidence = (
            classic_mint_evidence(req.token_mint)
            if req.token_program == TOKEN_PROGRAM_ID
            else None
        )
        return RiskEngine(lim or limits()).evaluate(
            req, port or portfolio(), now, token_program_evidence=evidence
        )

    def test_missing_token_program_evidence_fails_closed(self):
        decision = self.evaluate(req=request(token_program=None))
        self.assertFalse(decision.approved)
        self.assertIn("TOKEN_PROGRAM_EVIDENCE_UNAVAILABLE", decision.reasons)

    def test_clean_request_approved_with_sizing(self):
        d = self.evaluate()
        self.assertTrue(d.approved)
        self.assertEqual(d.reasons, ())
        self.assertIsNotNone(d.sizing)
        self.assertLessEqual(
            d.sizing.risk_amount_quote + d.sizing.estimated_fees_quote, D(10)
        )

    def test_emergency_stop_blocks_before_anything_else(self):
        d = self.evaluate(lim=limits(emergency_stop=True))
        self.assertEqual(d.reasons, ("EMERGENCY_STOP",))
        self.assertFalse(d.approved)

    def test_stale_portfolio_rejected_both_directions(self):
        self.assertEqual(
            self.evaluate(now=START + timedelta(seconds=61)).reasons,
            ("STALE_PORTFOLIO",),
        )
        self.assertEqual(
            self.evaluate(now=START - timedelta(seconds=1)).reasons,
            ("STALE_PORTFOLIO",),
        )
        self.assertTrue(self.evaluate(now=START + timedelta(seconds=60)).approved)

    def test_zero_equity_invalid(self):
        port = portfolio(equity_quote="0", peak_equity_quote="1")
        self.assertEqual(self.evaluate(port=port).reasons, ("INVALID_EQUITY",))

    def test_max_positions_boundary(self):
        pos = tuple(OpenPosition("m", D(1), D(1)) for _ in range(3))
        self.assertEqual(
            self.evaluate(port=portfolio(open_positions=pos)).reasons,
            ("MAX_POSITIONS",),
        )
        pos2 = pos[:2]
        self.assertTrue(self.evaluate(port=portfolio(open_positions=pos2)).approved)

    def test_drawdown_boundary_is_inclusive(self):
        port = portfolio(equity_quote="800", peak_equity_quote="1000")  # exactly 20 %
        self.assertIn("DRAWDOWN_LIMIT", self.evaluate(port=port).reasons)

    def test_cooldown_after_loss(self):
        port = portfolio(last_loss_at=START - timedelta(minutes=30))
        self.assertIn("COOLDOWN", self.evaluate(port=port).reasons)
        port2 = portfolio(last_loss_at=START - timedelta(hours=1))
        self.assertNotIn("COOLDOWN", self.evaluate(port=port2).reasons)

    def test_liquidity_spread_and_slippage_gates(self):
        self.assertIn(
            "LOW_LIQUIDITY", self.evaluate(req=request(liquidity_usd=D(9999))).reasons
        )
        self.assertIn(
            "SPREAD_TOO_WIDE", self.evaluate(req=request(spread_pct=D("1.01"))).reasons
        )
        self.assertIn(
            "SLIPPAGE_TOO_HIGH",
            self.evaluate(req=request(slippage_pct=D("1.5"))).reasons,
        )

    def test_exposure_limit_uses_notional_not_risk(self):
        # Risk per trade is ~10 but notional is ~100; a 150 cap blocks on exposure, not risk.
        port = portfolio(
            open_positions=(OpenPosition("m", D(50), D(2)),)
        )  # 100 open exposure
        d = self.evaluate(port=port, lim=limits(max_exposure_quote=D(150)))
        self.assertIn("EXPOSURE_LIMIT", d.reasons)
        self.assertNotIn("RISK_LIMIT", d.reasons)

    def test_zero_stop_distance_cannot_pass_levels_and_is_reported_by_engine(self):
        with self.assertRaises(DomainError):
            PriceLevels(D(2), D(2), D(3))

    def test_multiple_reasons_are_all_reported(self):
        d = self.evaluate(
            req=request(liquidity_usd=D(1), slippage_pct=D(9)),
            port=portfolio(last_loss_at=START - timedelta(minutes=1)),
        )
        self.assertEqual(
            set(d.reasons), {"COOLDOWN", "LOW_LIQUIDITY", "SLIPPAGE_TOO_HIGH"}
        )
        self.assertFalse(d.approved)

    def test_audit_payload_distinguishes_risk_and_exposure(self):
        req = request()
        d = self.evaluate(req=req)
        payload = d.as_audit_payload(req)
        self.assertIn("risk_amount_quote", payload)
        self.assertIn("exposure_quote", payload)
        self.assertNotEqual(payload["risk_amount_quote"], payload["exposure_quote"])

    def test_invalid_risk_percent_rejected_on_engine_construction(self):
        with self.assertRaises(DomainError):
            RiskEngine(limits(max_risk_per_trade_pct=D(0)))


class ReservationTest(unittest.TestCase):
    def test_reserve_respects_limit_and_release(self):
        r = ExposureReservations(D(100))
        self.assertTrue(r.try_reserve(D(60), D(0)))
        self.assertFalse(r.try_reserve(D(60), D(0)))
        r.release(D(60))
        self.assertTrue(r.try_reserve(D(60), D(0)))

    def test_open_exposure_counts_against_reservation(self):
        r = ExposureReservations(D(100))
        self.assertFalse(r.try_reserve(D(50), D(60)))

    def test_concurrent_reservations_never_overshoot(self):
        r = ExposureReservations(D(500))
        results = []
        lock = threading.Lock()

        def worker():
            ok = r.try_reserve(D(100), D(0))
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results.count(True), 5)
        self.assertEqual(r.reserved, D(500))

    def test_invalid_amounts_rejected(self):
        with self.assertRaises(DomainError):
            ExposureReservations(D(0))
        r = ExposureReservations(D(10))
        with self.assertRaises(DomainError):
            r.try_reserve(D(0), D(0))


class RiskConfigurationValidationTest(unittest.TestCase):
    def test_all_monetary_and_percentage_limits_are_validated(self):
        invalid = (
            {"max_exposure_quote": D(0)},
            {"max_exposure_quote": D("NaN")},
            {"max_drawdown_pct": D("Infinity")},
            {"min_liquidity_usd": D(-1)},
            {"max_spread_pct": D(101)},
            {"max_slippage_pct": D(-1)},
            {"fee_rate": D("1.01")},
            {"fee_rate": D("NaN")},
        )
        for overrides in invalid:
            with self.subTest(overrides=overrides), self.assertRaises(DomainError):
                limits(**overrides)

    def test_position_count_and_time_limits_are_validated(self):
        for overrides in (
            {"max_open_positions": 0},
            {"max_open_positions": True},
            {"loss_cooldown": timedelta(seconds=-1)},
            {"max_portfolio_age": timedelta(0)},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(DomainError):
                limits(**overrides)

    def test_valid_zero_optional_thresholds_remain_supported(self):
        configured = limits(
            min_liquidity_usd=D(0),
            max_drawdown_pct=D(0),
            max_spread_pct=D(0),
            max_slippage_pct=D(0),
            fee_rate=D(0),
        )
        self.assertEqual(configured.min_liquidity_usd, D(0))

    def test_trade_request_rejects_non_finite_and_out_of_range_market_data(self):
        for overrides in (
            {"liquidity_usd": D("NaN")},
            {"liquidity_usd": D(-1)},
            {"spread_pct": D("Infinity")},
            {"spread_pct": D(101)},
            {"slippage_pct": D(-1)},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(DomainError):
                request(**overrides)

    def test_trade_request_rejects_blank_mint(self):
        with self.assertRaises(DomainError):
            request(token_mint="   ")

    def test_exposure_reservations_reject_non_finite_values(self):
        with self.assertRaises(DomainError):
            ExposureReservations(D("NaN"))
        reservations = ExposureReservations(D(100))
        with self.assertRaises(DomainError):
            reservations.try_reserve(D(10), D("Infinity"))
        with self.assertRaises(DomainError):
            reservations.release(D(0))


if __name__ == "__main__":
    unittest.main()
