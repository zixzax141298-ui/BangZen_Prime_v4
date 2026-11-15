from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from bangzen_prime.core.errors import DomainError
from bangzen_prime.core.shared import DomainEvent
from bangzen_prime.discovery.tokens import pair_identity, token_identity
from bangzen_prime.notifications.notifications import format_signal_text
from bangzen_prime.scoring.signals import PriceLevels, Signal

MINT = "So11111111111111111111111111111111111111112"
PAIR = "PairAddressFixture"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


class VerifiedSignalPayloadTest(unittest.TestCase):
    def make_signal(self, **overrides):
        values = {
            "token_id": token_identity("solana", MINT),
            "pair_id": pair_identity("solana", PAIR),
            "score": Decimal("82.5"),
            "confidence": Decimal("0.78"),
            "levels": PriceLevels(
                Decimal("0.000012"),
                Decimal("0.000010"),
                Decimal("0.000016"),
            ),
            "created_at": NOW,
            "chain": "solana",
            "mint": MINT,
            "symbol": "TEST",
            "pair_address": PAIR,
            "dex_id": "raydium",
            "market_source": "DexScreener",
            "market_observed_at": NOW,
        }
        values.update(overrides)
        return Signal.accept(**values)

    def test_event_contains_validated_identity_and_market_provenance(self):
        signal = self.make_signal()
        event = signal.pull_events()[0]
        self.assertEqual(event.name, "SignalGenerated")
        self.assertEqual(event.payload["chain"], "solana")
        self.assertEqual(event.payload["mint"], MINT)
        self.assertEqual(event.payload["symbol"], "TEST")
        self.assertEqual(event.payload["pair_address"], PAIR)
        self.assertEqual(event.payload["dex_id"], "raydium")
        self.assertEqual(event.payload["market_source"], "DexScreener")
        self.assertEqual(event.payload["market_observed_at"], NOW.isoformat())
        self.assertEqual(event.payload["score"], "82.5")

    def test_rejects_mint_that_does_not_match_token_identity(self):
        with self.assertRaisesRegex(DomainError, "mint does not match"):
            self.make_signal(mint="11111111111111111111111111111111")

    def test_rejects_pair_that_does_not_match_pair_identity(self):
        with self.assertRaisesRegex(DomainError, "pair address does not match"):
            self.make_signal(pair_address="different-pair")

    def test_rejects_partial_market_metadata(self):
        with self.assertRaisesRegex(DomainError, "supplied together"):
            self.make_signal(market_source=None)

    def test_telegram_format_includes_verified_mint_and_provenance(self):
        event = self.make_signal().pull_events()[0]
        message = format_signal_text(event)
        self.assertIn(f"Mint: {MINT}", message)
        self.assertIn("Asset: TEST (solana)", message)
        self.assertIn("Market source: DexScreener", message)
        self.assertIn("Entry reference: 0.000012", message)
        self.assertIn("Heuristic score: 82.50", message)
        self.assertIn("Observed at: 2026-11-13T12:00:00+00:00", message)
        self.assertIn("\n", message)
        self.assertNotIn("Token id:", message)

    def test_legacy_event_never_mislabels_internal_uuid_as_mint(self):
        event = DomainEvent(
            name="SignalGenerated",
            payload={
                "signal_id": "signal-fixture",
                "token_id": "internal-uuid-fixture",
                "entry": "1",
                "stop_loss": "0.9",
                "take_profit": "1.2",
                "score": "70",
                "confidence": "0.7",
            },
            occurred_at=NOW,
        )
        message = format_signal_text(event)
        self.assertIn("mint unavailable", message)
        self.assertNotIn("Mint: internal-uuid-fixture", message)


if __name__ == "__main__":
    unittest.main()
