import unittest
from datetime import UTC, datetime
from decimal import Decimal

from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.adapters.market_data.jupiter_price import (
    JupiterPriceEvidenceAdapter,
    JupiterPriceMalformed,
)
from bangzen_prime.infrastructure.http import HttpResponse
from bangzen_prime.infrastructure.resilience.policies import (
    CircuitBreaker, HealthMonitor, ResilientCaller, RetryPolicy, TokenBucket,
)
from tests.support import SOL_MINT, TOKEN_MINT


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        import json
        return HttpResponse(200, json.dumps(self.payload).encode(), {})


def caller():
    return ResilientCaller(
        "jupiter_price_v3",
        retry=RetryPolicy(max_attempts=1),
        limiter=TokenBucket(rate_per_minute=600, capacity=10),
        breaker=CircuitBreaker("jupiter_price_v3", failure_threshold=3, recovery_seconds=1),
        health=HealthMonitor(),
        sleep=lambda _seconds: None,
    )


def payload(*, target_slot=990, quote_slot=995, target_price="0.02",
            quote_price="100", target_liquidity="50000", quote_liquidity="900000"):
    return {
        TOKEN_MINT: {
            "usdPrice": target_price, "liquidity": target_liquidity,
            "blockId": target_slot, "decimals": 6,
        },
        SOL_MINT: {
            "usdPrice": quote_price, "liquidity": quote_liquidity,
            "blockId": quote_slot, "decimals": 9,
        },
    }


class JupiterPriceEvidenceAdapterTests(unittest.TestCase):
    def make_adapter(self, response, *, current=1000, max_lag=20):
        transport = FakeTransport(response)
        adapter = JupiterPriceEvidenceAdapter(
            api_key="test-secret",
            transport=transport,
            caller=caller(),
            timeout=2,
            current_slot=lambda: current,
            clock=lambda: NOW,
            max_slot_lag=max_lag,
        )
        return adapter, transport

    def test_derives_quote_currency_rate_from_two_usd_prices(self):
        adapter, transport = self.make_adapter(payload())
        result = adapter.fetch_quote_price(mint=TOKEN_MINT, quote_mint=SOL_MINT)
        self.assertEqual(result.evidence.quote_per_token, Decimal("0.0002"))
        self.assertEqual(result.evidence.validation_status, "VERIFIED")
        self.assertEqual(result.target_block_slot, 990)
        self.assertEqual(result.quote_block_slot, 995)
        self.assertEqual(result.target_liquidity_usd, Decimal("50000"))
        self.assertEqual(result.evidence.slot, 990)
        self.assertIn("ids=", transport.requests[0].url)
        self.assertEqual(transport.requests[0].headers["x-api-key"], "test-secret")
        self.assertNotIn("test-secret", repr(result))

    def test_missing_target_or_quote_price_fails_closed(self):
        adapter, _ = self.make_adapter({TOKEN_MINT: payload()[TOKEN_MINT]})
        with self.assertRaises(JupiterPriceMalformed):
            adapter.fetch_quote_price(mint=TOKEN_MINT, quote_mint=SOL_MINT)

    def test_rejects_stale_target_or_quote_slot(self):
        for response in (payload(target_slot=900), payload(quote_slot=900)):
            adapter, _ = self.make_adapter(response, max_lag=20)
            with self.assertRaises(JupiterPriceMalformed):
                adapter.fetch_quote_price(mint=TOKEN_MINT, quote_mint=SOL_MINT)

    def test_rejects_future_slot(self):
        adapter, _ = self.make_adapter(payload(target_slot=1001))
        with self.assertRaises(JupiterPriceMalformed):
            adapter.fetch_quote_price(mint=TOKEN_MINT, quote_mint=SOL_MINT)

    def test_rejects_zero_negative_nan_and_boolean_prices_or_liquidity(self):
        for bad in ("0", "-1", "NaN", "Infinity", True, None):
            response = payload(target_price=bad)
            adapter, _ = self.make_adapter(response)
            with self.assertRaises(JupiterPriceMalformed):
                adapter.fetch_quote_price(mint=TOKEN_MINT, quote_mint=SOL_MINT)
        for bad in ("0", "-1", True, None):
            response = payload(quote_liquidity=bad)
            adapter, _ = self.make_adapter(response)
            with self.assertRaises(JupiterPriceMalformed):
                adapter.fetch_quote_price(mint=TOKEN_MINT, quote_mint=SOL_MINT)

    def test_rejects_invalid_slot_types(self):
        for bad in (True, -1, "990", None):
            response = payload(target_slot=bad)
            adapter, _ = self.make_adapter(response)
            with self.assertRaises(JupiterPriceMalformed):
                adapter.fetch_quote_price(mint=TOKEN_MINT, quote_mint=SOL_MINT)

    def test_rejects_invalid_current_slot_and_naive_clock(self):
        adapter, _ = self.make_adapter(payload(), current=True)
        with self.assertRaises(DomainError):
            adapter.fetch_quote_price(mint=TOKEN_MINT, quote_mint=SOL_MINT)
        adapter = JupiterPriceEvidenceAdapter(
            api_key="key", transport=FakeTransport(payload()), caller=caller(),
            timeout=2, current_slot=lambda: 1000,
            clock=lambda: datetime(2026, 11, 13), max_slot_lag=20,
        )
        with self.assertRaises(DomainError):
            adapter.fetch_quote_price(mint=TOKEN_MINT, quote_mint=SOL_MINT)

    def test_rejects_same_mint_and_invalid_policy(self):
        adapter, _ = self.make_adapter(payload())
        with self.assertRaises(DomainError):
            adapter.fetch_quote_price(mint=SOL_MINT, quote_mint=SOL_MINT)
        with self.assertRaises(DomainError):
            JupiterPriceEvidenceAdapter(
                api_key="key", transport=FakeTransport(payload()), caller=caller(),
                timeout=2, current_slot=lambda: 1000, clock=lambda: NOW, max_slot_lag=-1,
            )

    def test_rejects_malformed_provider_payload(self):
        for response in (None, [], {TOKEN_MINT: "not-object"}):
            adapter, _ = self.make_adapter(response)
            with self.assertRaises(JupiterPriceMalformed):
                adapter.fetch_quote_price(mint=TOKEN_MINT, quote_mint=SOL_MINT)

    def test_rejects_missing_or_blank_api_key(self):
        with self.assertRaises(DomainError):
            JupiterPriceEvidenceAdapter(
                api_key="", transport=FakeTransport(payload()), caller=caller(),
                timeout=2, current_slot=lambda: 1000, clock=lambda: NOW, max_slot_lag=20,
            )


if __name__ == "__main__":
    unittest.main()
