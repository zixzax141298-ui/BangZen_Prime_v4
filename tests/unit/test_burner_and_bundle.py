"""Regression: plaintext burner and tip signing remain removed/locked."""

from __future__ import annotations

import importlib.util
import unittest

from bangzen_prime.infrastructure.adapters.chain.jito_bundle import (
    BroadcastRefused,
    build_tip_transaction,
    relay_bundle,
)
from bangzen_prime.infrastructure.adapters.execution.signing import SigningDisabled
from bangzen_prime.infrastructure.http import HttpRequest, HttpResponse
from bangzen_prime.infrastructure.resilience.policies import (
    CircuitBreaker,
    FakeClock,
    HealthMonitor,
    ResilientCaller,
    RetryPolicy,
    TokenBucket,
)


class RemovedBurnerSurfaceTest(unittest.TestCase):
    def test_burner_wallet_module_absent(self):
        self.assertIsNone(
            importlib.util.find_spec(
                "bangzen_prime.infrastructure.adapters.execution.burner_wallet"
            )
        )

    def test_ed25519_module_absent(self):
        self.assertIsNone(
            importlib.util.find_spec(
                "bangzen_prime.infrastructure.adapters.execution.ed25519"
            )
        )

    def test_build_tip_transaction_is_disabled(self):
        with self.assertRaises(SigningDisabled):
            build_tip_transaction(
                object(),
                tip_account="11111111111111111111111111111111",
                tip_lamports=1000,
                recent_blockhash="11111111111111111111111111111111",
            )


class RelayBundleLockTest(unittest.TestCase):
    def test_relay_refuses_without_allow_broadcast(self):
        clock = FakeClock()
        caller = ResilientCaller(
            "jito",
            retry=RetryPolicy(max_attempts=1),
            limiter=TokenBucket(rate_per_minute=60, clock=clock),
            breaker=CircuitBreaker("jito", clock=clock),
            health=HealthMonitor(),
            sleep=lambda s: None,
            clock=clock,
        )

        def transport(request: HttpRequest) -> HttpResponse:
            raise AssertionError("must not contact network when broadcast refused")

        with self.assertRaises(BroadcastRefused):
            relay_bundle(
                ["dGVzdA=="],
                transport=transport,
                caller=caller,
                timeout=1.0,
                block_engine="https://example.invalid",
                allow_broadcast=False,
            )


if __name__ == "__main__":
    unittest.main()
