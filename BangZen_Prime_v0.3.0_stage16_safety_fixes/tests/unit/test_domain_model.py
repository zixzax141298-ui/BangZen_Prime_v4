import unittest
import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from bangzen_prime.core.errors import DomainError
from bangzen_prime.core.shared import AggregateRoot, DomainEvent, Entity
from bangzen_prime.discovery.tokens import (
    PairSnapshot,
    SafetyAssessment,
    Token,
    token_identity,
)
from bangzen_prime.risk.risk import OpenPosition, PortfolioSnapshot, size_position
from bangzen_prime.scoring.signals import (
    PriceLevels,
    RejectReason,
    Signal,
    SignalStatus,
)
from tests.support import PAIR_ADDRESS, SOL_MINT, START, TOKEN_MINT


class TokenIdentityTest(unittest.TestCase):
    def test_same_chain_and_address_give_same_identity(self):
        a = Token(chain="solana", mint=TOKEN_MINT, symbol="ABC")
        b = Token(chain="solana", mint=TOKEN_MINT, symbol="ABC", name="other")
        self.assertEqual(a.id, b.id)
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertEqual(a.id, token_identity("solana", TOKEN_MINT))

    def test_different_mints_are_not_equal(self):
        self.assertNotEqual(
            Token(chain="solana", mint=TOKEN_MINT, symbol="A"),
            Token(chain="solana", mint=SOL_MINT, symbol="B"),
        )

    def test_unsupported_chain_rejected(self):
        with self.assertRaises(DomainError):
            Token(chain="ethereum", mint=TOKEN_MINT, symbol="A")

    def test_invalid_mint_rejected(self):
        for mint in ("", "0OIl" * 10, "short", "E" * 50):
            with self.subTest(mint=mint), self.assertRaises(DomainError):
                Token(chain="solana", mint=mint, symbol="A")

    def test_symbol_bounds(self):
        with self.assertRaises(DomainError):
            Token(chain="solana", mint=TOKEN_MINT, symbol="")
        with self.assertRaises(DomainError):
            Token(chain="solana", mint=TOKEN_MINT, symbol="X" * 33)

    def test_entity_id_must_be_uuid(self):
        with self.assertRaises(DomainError):
            Entity("not-a-uuid")


class PairSnapshotTest(unittest.TestCase):
    def make(self, **overrides):
        base = dict(
            chain="solana",
            pair_address=PAIR_ADDRESS,
            dex_id="raydium",
            base_mint=TOKEN_MINT,
            base_symbol="T",
            price_usd="1.5",
            liquidity_usd="100",
            volume_24h_usd="10",
            observed_at=START,
        )
        base.update(overrides)
        return PairSnapshot.create(**base)

    def test_valid_pair_ids_are_consistent_with_token(self):
        pair = self.make()
        self.assertEqual(pair.token_id, token_identity("solana", TOKEN_MINT))
        self.assertEqual(pair.pair_id, self.make().pair_id)

    def test_nan_price_and_infinite_liquidity_rejected(self):
        with self.assertRaises(DomainError):
            self.make(price_usd="NaN")
        with self.assertRaises(DomainError):
            self.make(liquidity_usd="Infinity")

    def test_zero_price_rejected_negative_liquidity_rejected(self):
        with self.assertRaises(DomainError):
            self.make(price_usd="0")
        with self.assertRaises(DomainError):
            self.make(liquidity_usd="-1")

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(DomainError):
            self.make(observed_at=datetime(2026, 1, 1))

    def test_staleness_boundary(self):
        pair = self.make()
        self.assertFalse(pair.is_stale(START + timedelta(seconds=120), 120))
        self.assertTrue(pair.is_stale(START + timedelta(seconds=121), 120))
        self.assertTrue(pair.is_stale(START - timedelta(seconds=1), 120))

    def test_utc_normalisation(self):
        at_utc_plus_7 = datetime(2026, 1, 1, 19, 0, tzinfo=timezone(timedelta(hours=7)))
        pair = self.make(observed_at=at_utc_plus_7)
        self.assertEqual(pair.observed_at, datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
        self.assertEqual(pair.observed_at.utcoffset(), timedelta(0))


class SafetyAssessmentTest(unittest.TestCase):
    def make(self, risk="10", rugged=False):
        return SafetyAssessment.create(
            chain="solana",
            mint=TOKEN_MINT,
            risk_score=risk,
            rugged=rugged,
            source="rugcheck",
            checked_at=START,
        )

    def test_rugged_is_rejected_before_score_check(self):
        self.assertEqual(
            self.make(risk="0", rugged=True).rejection_reason(Decimal(60)), "RUGGED"
        )

    def test_risk_boundary_is_inclusive_pass(self):
        self.assertIsNone(self.make(risk="60").rejection_reason(Decimal(60)))
        self.assertEqual(
            self.make(risk="60.01").rejection_reason(Decimal(60)), "RISK_TOO_HIGH"
        )

    def test_rugged_must_be_bool(self):
        with self.assertRaises(DomainError):
            SafetyAssessment.create(
                chain="solana",
                mint=TOKEN_MINT,
                risk_score="1",
                rugged="yes",
                source="x",
                checked_at=START,
            )

    def test_risk_out_of_range_rejected(self):
        with self.assertRaises(DomainError):
            self.make(risk="101")


class PriceLevelsTest(unittest.TestCase):
    def test_long_geometry_enforced(self):
        PriceLevels(Decimal(2), Decimal("1.5"), Decimal(3))
        for stop, entry, target in (
            ("2", "2", "3"),
            ("2.1", "2", "3"),
            ("1", "2", "2"),
            ("1", "3", "2"),
        ):
            with (
                self.subTest(stop=stop, entry=entry, target=target),
                self.assertRaises(DomainError),
            ):
                PriceLevels(Decimal(entry), Decimal(stop), Decimal(target))

    def test_zero_or_negative_stop_rejected(self):
        with self.assertRaises(DomainError):
            PriceLevels(Decimal(2), Decimal(0), Decimal(3))
        with self.assertRaises(DomainError):
            PriceLevels(Decimal(2), Decimal(-1), Decimal(3))

    def test_risk_reward(self):
        levels = PriceLevels(Decimal(2), Decimal("1.8"), Decimal("2.3"))
        self.assertEqual(levels.risk_reward, Decimal("1.5"))


class SignalTest(unittest.TestCase):
    def levels(self):
        return PriceLevels(Decimal(2), Decimal("1.8"), Decimal("2.3"))

    def test_accepted_signal_buffers_one_event_and_pulls_once(self):
        signal = Signal.accept(
            token_id=uuid.uuid4(),
            pair_id=uuid.uuid4(),
            score=Decimal(60),
            confidence=Decimal("0.6"),
            levels=self.levels(),
            created_at=START,
        )
        events = signal.pull_events()
        self.assertEqual([e.name for e in events], ["SignalGenerated"])
        self.assertEqual(events[0].payload["label"], "SIGNAL_ONLY")
        self.assertEqual(signal.pull_events(), [])

    def test_rejected_signal_has_no_events_and_needs_reason(self):
        signal = Signal.reject(
            token_id=uuid.uuid4(),
            pair_id=uuid.uuid4(),
            score=Decimal(0),
            reasons=(RejectReason.RUGGED,),
            created_at=START,
        )
        self.assertEqual(signal.status, SignalStatus.REJECTED)
        self.assertEqual(signal.pull_events(), [])
        with self.assertRaises(DomainError):
            Signal.reject(
                token_id=uuid.uuid4(),
                pair_id=uuid.uuid4(),
                score=Decimal(0),
                reasons=(),
                created_at=START,
            )

    def test_accepted_requires_levels_and_valid_confidence(self):
        with self.assertRaises(DomainError):
            Signal(
                token_id=uuid.uuid4(),
                pair_id=uuid.uuid4(),
                status=SignalStatus.ACCEPTED,
                score=Decimal(60),
                reasons=(),
                created_at=START,
            )
        with self.assertRaises(DomainError):
            Signal.accept(
                token_id=uuid.uuid4(),
                pair_id=uuid.uuid4(),
                score=Decimal(60),
                confidence=Decimal("1.5"),
                levels=self.levels(),
                created_at=START,
            )

    def test_signal_identity_equality(self):
        sid = uuid.uuid4()
        a = Signal(
            token_id=uuid.uuid4(),
            pair_id=uuid.uuid4(),
            status=SignalStatus.REJECTED,
            score=Decimal(0),
            reasons=(RejectReason.LOW_SCORE,),
            created_at=START,
            signal_id=sid,
        )
        b = Signal(
            token_id=uuid.uuid4(),
            pair_id=uuid.uuid4(),
            status=SignalStatus.REJECTED,
            score=Decimal(0),
            reasons=(RejectReason.LOW_SCORE,),
            created_at=START,
            signal_id=sid,
        )
        self.assertEqual(a, b)

    def test_domain_event_requires_name(self):
        with self.assertRaises(DomainError):
            DomainEvent(name="", payload={}, occurred_at=START)

    def test_aggregate_is_entity(self):
        self.assertTrue(issubclass(Signal, AggregateRoot))


class RiskMathTest(unittest.TestCase):
    def test_risk_plus_fees_equals_budget(self):
        levels = PriceLevels(Decimal(2), Decimal("1.8"), Decimal("2.3"))
        sizing = size_position(
            equity_quote="1000", risk_pct="1", levels=levels, fee_rate=Decimal("0.001")
        )
        self.assertAlmostEqual(
            sizing.risk_amount_quote + sizing.estimated_fees_quote,
            Decimal(10),
            places=20,
        )
        self.assertAlmostEqual(
            sizing.risk_amount_quote,
            sizing.size_units * levels.risk_per_unit,
            places=20,
        )
        self.assertAlmostEqual(
            sizing.exposure_quote, sizing.size_units * levels.entry, places=20
        )

    def test_exposure_and_risk_are_distinct(self):
        levels = PriceLevels(Decimal(2), Decimal("1.8"), Decimal("2.3"))
        sizing = size_position(
            equity_quote="1000", risk_pct="1", levels=levels, fee_rate=Decimal(0)
        )
        self.assertNotEqual(sizing.risk_amount_quote, sizing.exposure_quote)

    def test_invalid_equity_and_risk_pct_rejected(self):
        levels = PriceLevels(Decimal(2), Decimal("1.8"), Decimal("2.3"))
        with self.assertRaises(DomainError):
            size_position(
                equity_quote="0", risk_pct="1", levels=levels, fee_rate=Decimal(0)
            )
        with self.assertRaises(DomainError):
            size_position(
                equity_quote="1000", risk_pct="0", levels=levels, fee_rate=Decimal(0)
            )

    def test_portfolio_drawdown_and_exposure(self):
        pos = (
            OpenPosition("m", Decimal(10), Decimal(2)),
            OpenPosition("n", Decimal(5), Decimal(4)),
        )
        snap = PortfolioSnapshot.create(
            equity_quote="800",
            peak_equity_quote="1000",
            open_positions=pos,
            as_of=START,
        )
        self.assertEqual(snap.open_count, 2)
        self.assertEqual(snap.open_exposure_quote, Decimal(40))
        self.assertEqual(snap.drawdown_pct, Decimal(20))

    def test_peak_below_equity_rejected(self):
        with self.assertRaises(DomainError):
            PortfolioSnapshot.create(
                equity_quote="1100",
                peak_equity_quote="1000",
                open_positions=(),
                as_of=START,
            )

    def test_naive_as_of_rejected(self):
        with self.assertRaises(DomainError):
            PortfolioSnapshot.create(
                equity_quote="1",
                peak_equity_quote="1",
                open_positions=(),
                as_of=datetime(2026, 1, 1),
            )


if __name__ == "__main__":
    unittest.main()
