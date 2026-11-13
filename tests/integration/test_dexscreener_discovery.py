"""DexScreener latest token profile discovery adapter tests."""

import unittest

from bangzen_prime.errors import ExternalServiceError
from bangzen_prime.infrastructure.adapters.market_data.dexscreener_discovery import (
    DexScreenerDiscoveryAdapter,
)
from bangzen_prime.infrastructure.http import HttpResponse
from bangzen_prime.infrastructure.resilience.policies import (
    CircuitBreaker, FakeClock, HealthMonitor, ResilientCaller, RetryPolicy, TokenBucket,
)
from tests.support import START, TOKEN_MINT, RecordingTransport, json_response


BASE = "https://api.dexscreener.com"


def make_caller(clock):
    return ResilientCaller(
        "discovery",
        retry=RetryPolicy(max_attempts=2, base_delay_seconds=0.0),
        limiter=TokenBucket(rate_per_minute=6000, clock=clock),
        breaker=CircuitBreaker("discovery", clock=clock),
        health=HealthMonitor(),
        sleep=lambda _: None,
        clock=clock,
    )


class DexScreenerDiscoveryTest(unittest.TestCase):
    def adapter(self, handler):
        clock = FakeClock(START)
        transport = RecordingTransport(handler)
        adapter = DexScreenerDiscoveryAdapter(
            base_url=BASE, transport=transport, caller=make_caller(clock), timeout=5
        )
        return adapter, transport

    def test_returns_unique_valid_solana_candidates(self):
        payload = [
            {"chainId": "ethereum", "tokenAddress": TOKEN_MINT},
            {"chainId": "solana", "tokenAddress": "not-an-address"},
            {"chainId": "solana", "tokenAddress": TOKEN_MINT},
            {"chainId": "solana", "tokenAddress": TOKEN_MINT},
        ]
        adapter, transport = self.adapter(lambda url: json_response(payload))

        self.assertEqual(adapter.fetch_candidates(limit=5), [TOKEN_MINT])
        self.assertEqual(
            transport.calls, [f"{BASE}/token-profiles/latest/v1"]
        )

    def test_caps_candidates_to_requested_limit(self):
        second = "So11111111111111111111111111111111111111112"
        payload = [
            {"chainId": "solana", "tokenAddress": TOKEN_MINT},
            {"chainId": "solana", "tokenAddress": second},
        ]
        adapter, _ = self.adapter(lambda url: json_response(payload))

        self.assertEqual(adapter.fetch_candidates(limit=1), [TOKEN_MINT])

    def test_unexpected_payload_fails_closed(self):
        adapter, _ = self.adapter(lambda url: json_response({"profiles": []}))

        with self.assertRaises(ExternalServiceError):
            adapter.fetch_candidates()

    def test_http_client_error_is_not_retried(self):
        adapter, transport = self.adapter(lambda url: HttpResponse(404, b"", {}))

        with self.assertRaises(ExternalServiceError):
            adapter.fetch_candidates()
        self.assertEqual(len(transport.calls), 1)

    def test_invalid_limit_rejected_before_network(self):
        adapter, transport = self.adapter(lambda url: json_response([]))

        with self.assertRaises(ValueError):
            adapter.fetch_candidates(limit=101)
        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()
