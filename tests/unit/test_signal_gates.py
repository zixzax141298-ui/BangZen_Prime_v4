import asyncio
import unittest
from datetime import timedelta
from decimal import Decimal

from bangzen_prime.application.scoring import ScoreBreakdown, score_token
from bangzen_prime.application.use_cases import (
    SignalPolicy,
    build_signal,
    select_best_pair,
)
from bangzen_prime.bootstrap import build_container
from bangzen_prime.domain.signals import RejectReason, SignalStatus
from bangzen_prime.domain.tokens import PairSnapshot, Token
from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.infrastructure.persistence.sqlite.repositories import UnitOfWork
from bangzen_prime.settings import Settings
from tests.support import (
    PAIR_ADDRESS,
    SOL_MINT,
    START,
    TOKEN_MINT,
    clock_at,
    json_response,
)

D = Decimal
POLICY = SignalPolicy(
    min_liquidity_usd=D(10000), max_risk_score=D(60), max_data_age_seconds=120
)


def pair(
    liquidity="200000",
    volume="300000",
    mint=TOKEN_MINT,
    chain="solana",
    addr=PAIR_ADDRESS,
    pair_created_at=None,
):
    return PairSnapshot.create(
        chain=chain,
        pair_address=addr,
        dex_id="raydium",
        base_mint=mint,
        base_symbol="T",
        price_usd="1",
        liquidity_usd=liquidity,
        volume_24h_usd=volume,
        observed_at=START,
        pair_created_at=pair_created_at,
    )


def seeded_repos(prices):
    db = Database(":memory:")
    db.migrate()
    uow = UnitOfWork(db)
    token = Token(chain="solana", mint=TOKEN_MINT, symbol="T")
    with uow.begin() as repos:
        repos.tokens.upsert(token, START)
        repos.pairs.upsert(pair())
        for price in prices:
            repos.prices.append(token.id, D(price), START)
    return db, uow, token


def run_build(prices, p=None, policy=POLICY):
    db, uow, token = seeded_repos(prices)
    with uow.begin() as repos:
        return asyncio.run(
            build_signal(
                repos=repos,
                token=token,
                pair=p or pair(),
                risk_score=D(10),
                policy=policy,
                now=START,
            )
        )


RISING = [str(D(1) + D("0.01") * i) for i in range(20)]


class BuildSignalGatesTest(unittest.TestCase):
    def test_rising_series_accepts_with_long_geometry(self):
        signal = run_build(RISING)
        self.assertIs(signal.status, SignalStatus.ACCEPTED)
        self.assertTrue(
            signal.levels.stop_loss < signal.levels.entry < signal.levels.take_profit
        )
        self.assertEqual(signal.levels.risk_reward, D("1.5"))

    def test_insufficient_history_reason(self):
        signal = run_build(RISING[:10])
        self.assertEqual(signal.reasons, (RejectReason.INSUFFICIENT_HISTORY,))

    def test_flat_series_has_no_volatility(self):
        signal = run_build(["1"] * 20)
        self.assertIn(RejectReason.NO_VOLATILITY, signal.reasons)
        self.assertIs(signal.status, SignalStatus.REJECTED)

    def test_low_liquidity_reason_is_structured(self):
        signal = run_build(
            RISING, p=pair(liquidity="5000", pair_created_at=START - timedelta(days=2))
        )
        self.assertIn(RejectReason.LOW_LIQUIDITY, signal.reasons)

    def test_launch_phase_can_be_watched_without_fixed_liquidity_floor(self):
        launch_pair = pair(
            liquidity="5000", pair_created_at=START - timedelta(minutes=5)
        )
        signal = run_build(RISING, p=launch_pair)
        self.assertIs(signal.status, SignalStatus.ACCEPTED)
        self.assertNotIn(RejectReason.LOW_LIQUIDITY, signal.reasons)

    def test_unknown_pair_age_does_not_trigger_liquidity_floor_by_itself(self):
        unknown_pair = pair(liquidity="5000")
        signal = run_build(RISING, p=unknown_pair)
        self.assertIs(signal.status, SignalStatus.ACCEPTED)
        self.assertNotIn(RejectReason.LOW_LIQUIDITY, signal.reasons)

    def test_low_liquidity_still_applies_after_early_phase(self):
        growth_pair = pair(liquidity="5000", pair_created_at=START - timedelta(days=2))
        signal = run_build(RISING, p=growth_pair)
        self.assertIn(RejectReason.LOW_LIQUIDITY, signal.reasons)

    def test_low_score_reason_for_weak_market(self):
        signal = run_build(
            RISING,
            p=pair(liquidity="10000", volume="0"),
            policy=SignalPolicy(D(0), D(60), 120),
        )
        self.assertIn(RejectReason.LOW_SCORE, signal.reasons)

    def test_multiple_gates_report_multiple_reasons(self):
        signal = run_build(
            ["1"] * 20,
            p=pair(
                liquidity="1", volume="0", pair_created_at=START - timedelta(days=2)
            ),
        )
        self.assertIn(RejectReason.NO_VOLATILITY, signal.reasons)
        self.assertIn(RejectReason.LOW_LIQUIDITY, signal.reasons)

    def test_select_best_pair_picks_highest_liquidity_for_matching_token_only(self):
        pairs = [
            pair(liquidity="100"),
            pair(liquidity="900", addr="ABCDEF"),
            pair(liquidity="5000", mint=SOL_MINT),
            pair(liquidity="7000", chain="solana", addr="ZZZ", mint=SOL_MINT),
        ]
        chosen = select_best_pair(pairs, "solana", TOKEN_MINT)
        self.assertEqual(chosen.pair_address, "ABCDEF")
        self.assertIsNone(select_best_pair([pair(mint=SOL_MINT)], "solana", TOKEN_MINT))

    def test_score_breakdown_confidence_is_total_over_100(self):
        b = ScoreBreakdown(D(1), D(1), D(1), D(1), D(45))
        self.assertEqual(b.confidence, D("0.45"))

    def test_score_token_momentum_extremes(self):
        centre = score_token(
            liquidity_usd=D(0), volume_24h_usd=D(0), risk_score=D(0), rsi_value=D(55)
        )
        far = score_token(
            liquidity_usd=D(0), volume_24h_usd=D(0), risk_score=D(0), rsi_value=D(0)
        )
        self.assertEqual(centre.momentum, D("100.00"))
        self.assertEqual(far.momentum, D("0.00"))
        self.assertEqual(far.total, D("30.00") - D("30.00") + far.total)

    def test_rsi_out_of_range_rejected_by_scoring(self):
        with self.assertRaises(DomainError):
            score_token(
                liquidity_usd=D(0),
                volume_24h_usd=D(0),
                risk_score=D(0),
                rsi_value=D(101),
            )


class ContainerWiringTest(unittest.TestCase):
    def test_container_wires_optional_lunarcrush_without_making_a_request(self):
        settings = Settings.from_env(
            {"BANGZEN_LUNARCRUSH_API_KEY": "SYNTHETIC-TEST-KEY"}
        )
        container = build_container(
            settings,
            transport=lambda url, timeout: json_response([]),
            clock=clock_at(0),
            sleep=lambda seconds: None,
            db_path=":memory:",
        )
        self.assertIsNotNone(container.intel.lunarcrush)
        self.assertEqual(container.health.snapshot(), {})

    def test_container_exposes_expected_components(self):
        c = build_container(
            Settings(),
            transport=lambda u, t: json_response([]),
            clock=clock_at(0),
            sleep=lambda s: None,
            db_path=":memory:",
        )
        self.assertIsNotNone(c.scan)
        self.assertIsNotNone(c.worker)
        self.assertEqual(c.health.snapshot(), {})
        self.assertEqual(c.bus.dispatch.__name__, "dispatch")


if __name__ == "__main__":
    unittest.main()
