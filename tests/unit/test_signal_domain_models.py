from __future__ import annotations

import unittest
import uuid
from decimal import Decimal

from bangzen_prime.domain.signals import (
    PriceLevels,
    RejectReason,
    ResilienceConfig,
    ResiliencePolicy,
    Signal,
    SignalStatus,
)
from bangzen_prime.errors import DomainError
from tests.support import START

D = Decimal


class PriceLevelsTest(unittest.TestCase):
    def test_valid_long_geometry_and_risk_reward(self):
        levels = PriceLevels(D("2"), D("1.8"), D("2.4"))
        self.assertEqual(levels.risk_per_unit, D("0.2"))
        self.assertEqual(levels.reward_per_unit, D("0.4"))
        self.assertEqual(levels.risk_reward, D("2"))

    def test_invalid_long_geometry_is_rejected(self):
        for values in (
            (D("2"), D("2"), D("3")),
            (D("2"), D("1"), D("2")),
            (D("2"), D("3"), D("4")),
            (D("NaN"), D("1"), D("3")),
        ):
            with self.subTest(values=values), self.assertRaises(DomainError):
                PriceLevels(*values)


class SignalAggregateTest(unittest.TestCase):
    def setUp(self):
        self.token_id = uuid.uuid4()
        self.pair_id = uuid.uuid4()

    def test_accept_creates_signal_event_and_validated_levels(self):
        signal = Signal.accept(
            token_id=self.token_id, pair_id=self.pair_id, score=D("90"),
            confidence=D("0.9"), levels=PriceLevels(D("2"), D("1.8"), D("2.4")),
            created_at=START,
        )
        self.assertEqual(signal.status, SignalStatus.ACCEPTED)
        self.assertEqual(len(signal.pull_events()), 1)
        self.assertEqual(signal.levels.entry, D("2"))

    def test_reject_requires_reason_codes(self):
        signal = Signal.reject(
            token_id=self.token_id, pair_id=self.pair_id, score=D("10"),
            reasons=(RejectReason.LOW_LIQUIDITY,), created_at=START,
        )
        self.assertEqual(signal.status, SignalStatus.REJECTED)
        with self.assertRaises(DomainError):
            Signal.reject(
                token_id=self.token_id, pair_id=self.pair_id, score=D("10"),
                reasons=(), created_at=START,
            )

    def test_watch_signal_is_not_execution_approval(self):
        signal = Signal(
            token_id=self.token_id, pair_id=self.pair_id, status=SignalStatus.WATCH,
            score=D("50"), reasons=(RejectReason.PHASE_WATCH_ONLY,), created_at=START,
        )
        self.assertEqual(signal.status, SignalStatus.WATCH)
        self.assertIsNone(signal.levels)
        self.assertIsNone(signal.confidence)

    def test_accepted_signal_requires_levels_confidence_and_no_reasons(self):
        with self.assertRaises(DomainError):
            Signal(
                token_id=self.token_id, pair_id=self.pair_id, status=SignalStatus.ACCEPTED,
                score=D("90"), reasons=(), created_at=START,
            )


class ResilienceDomainPolicyTest(unittest.TestCase):
    def test_valid_resilience_config(self):
        policy = ResiliencePolicy(failure_threshold=3, recovery_seconds=15)
        config = ResilienceConfig(policy, policy, policy, policy, policy)
        self.assertEqual(config.market_breaker.failure_threshold, 3)

    def test_invalid_policy_or_unvalidated_config_is_rejected(self):
        with self.assertRaises(DomainError):
            ResiliencePolicy(failure_threshold=0)
        with self.assertRaises(DomainError):
            ResiliencePolicy(recovery_seconds=float("nan"))
        with self.assertRaises(DomainError):
            ResilienceConfig(None, None, None, None, None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
