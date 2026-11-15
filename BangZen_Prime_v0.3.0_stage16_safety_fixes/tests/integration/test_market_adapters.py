import unittest
from datetime import timedelta
from decimal import Decimal

from bangzen_prime.core.errors import ExternalServiceError
from bangzen_prime.data.http import HttpResponse, TransportTimeout
from bangzen_prime.data.providers.dexscreener import (
    DexScreenerAdapter,
)
from bangzen_prime.data.providers.intel import SolanaTrackerAdapter
from bangzen_prime.data.providers.rugcheck import RugCheckAdapter
from bangzen_prime.data.retry.policies import (
    CircuitBreaker,
    FakeClock,
    HealthMonitor,
    ResilientCaller,
    RetryPolicy,
    TokenBucket,
)
from tests.support import (
    PAIR_ADDRESS,
    START,
    TOKEN_MINT,
    RecordingTransport,
    json_response,
    pair_payload,
    safety_payload,
)

BASE = "https://api.dexscreener.com"
RC_BASE = "https://api.rugcheck.xyz/v1"


def make_caller(clock, sleeps):
    return ResilientCaller(
        "svc",
        retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.0),
        limiter=TokenBucket(rate_per_minute=6000, clock=clock),
        breaker=CircuitBreaker("svc", clock=clock),
        health=HealthMonitor(),
        sleep=sleeps.append,
        clock=clock,
    )


class DexScreenerTest(unittest.TestCase):
    def adapter(self, handler, clock=None):
        clock = clock or FakeClock(START)
        sleeps = []
        transport = RecordingTransport(handler)
        adapter = DexScreenerAdapter(
            base_url=BASE,
            transport=transport,
            caller=make_caller(clock, sleeps),
            timeout=5,
            clock=clock.now,
        )
        return adapter, transport, sleeps

    def test_valid_response_yields_snapshot_with_decimal_price(self):
        adapter, transport, _ = self.adapter(
            lambda url: json_response([pair_payload(price="0.0012")])
        )
        pairs = adapter.fetch_pairs("solana", TOKEN_MINT)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].price_usd, Decimal("0.0012"))
        self.assertEqual(pairs[0].pair_address, PAIR_ADDRESS)
        self.assertEqual(
            transport.calls, [f"{BASE}/token-pairs/v1/solana/{TOKEN_MINT}"]
        )

    def test_pair_creation_timestamp_is_parsed_from_milliseconds(self):
        payload = pair_payload()
        payload["pairCreatedAt"] = int(START.timestamp() * 1000)
        adapter, _, _ = self.adapter(lambda url: json_response([payload]))
        pair = adapter.fetch_pairs("solana", TOKEN_MINT)[0]
        self.assertEqual(pair.pair_created_at, START)

    def test_missing_pair_creation_timestamp_remains_unknown(self):
        adapter, _, _ = self.adapter(lambda url: json_response([pair_payload()]))
        pair = adapter.fetch_pairs("solana", TOKEN_MINT)[0]
        self.assertIsNone(pair.pair_created_at)

    def test_empty_list_is_valid_and_empty(self):
        adapter, _, _ = self.adapter(lambda url: json_response([]))
        self.assertEqual(adapter.fetch_pairs("solana", TOKEN_MINT), [])

    def test_non_list_body_is_malformed_non_retryable(self):
        adapter, _, _ = self.adapter(lambda url: json_response({"pairs": []}))
        with self.assertRaises(ExternalServiceError) as ctx:
            adapter.fetch_pairs("solana", TOKEN_MINT)
        self.assertFalse(ctx.exception.retryable)

    def test_wrong_chain_and_wrong_base_token_are_skipped(self):
        other_chain = pair_payload(chain="ethereum")
        other_token = pair_payload(mint="So11111111111111111111111111111111111111112")
        good = pair_payload()
        adapter, _, _ = self.adapter(
            lambda url: json_response([other_chain, other_token, good])
        )
        self.assertEqual(len(adapter.fetch_pairs("solana", TOKEN_MINT)), 1)

    def test_nan_and_infinite_values_are_skipped(self):
        nan_price = pair_payload(price="NaN")
        inf_liq = pair_payload(liquidity=float("inf"))
        bad_float = pair_payload()
        bad_float["priceUsd"] = None
        good = pair_payload()
        adapter, _, _ = self.adapter(
            lambda url: json_response([nan_price, inf_liq, bad_float, good])
        )
        self.assertEqual(len(adapter.fetch_pairs("solana", TOKEN_MINT)), 1)

    def test_zero_price_entry_is_skipped_not_fatal(self):
        adapter, _, _ = self.adapter(
            lambda url: json_response([pair_payload(price="0"), pair_payload()])
        )
        self.assertEqual(len(adapter.fetch_pairs("solana", TOKEN_MINT)), 1)

    def test_missing_pair_address_is_skipped(self):
        broken = pair_payload()
        del broken["pairAddress"]
        adapter, _, _ = self.adapter(lambda url: json_response([broken]))
        self.assertEqual(adapter.fetch_pairs("solana", TOKEN_MINT), [])

    def test_timeout_retried_then_error_surfaces(self):
        adapter, transport, sleeps = self.adapter(lambda url: TransportTimeout())
        with self.assertRaises(ExternalServiceError) as ctx:
            adapter.fetch_pairs("solana", TOKEN_MINT)
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(len(transport.calls), 3)

    def test_429_retried_with_retry_after_then_success(self):
        responses = [
            HttpResponse(429, b"", {"Retry-After": "2"}),
            json_response([pair_payload()]),
        ]
        adapter, transport, sleeps = self.adapter(lambda url: responses.pop(0))
        self.assertEqual(len(adapter.fetch_pairs("solana", TOKEN_MINT)), 1)
        self.assertEqual(len(transport.calls), 2)

    def test_4xx_not_retried(self):
        adapter, transport, _ = self.adapter(lambda url: HttpResponse(400, b"", {}))
        with self.assertRaises(ExternalServiceError):
            adapter.fetch_pairs("solana", TOKEN_MINT)
        self.assertEqual(len(transport.calls), 1)

    def test_invalid_input_rejected_before_any_call(self):
        adapter, transport, _ = self.adapter(lambda url: json_response([]))
        with self.assertRaises(Exception):
            adapter.fetch_pairs("ethereum", TOKEN_MINT)
        with self.assertRaises(Exception):
            adapter.fetch_pairs("solana", "bad address")
        self.assertEqual(transport.calls, [])

    def test_stale_observation_timestamp_comes_from_injected_clock(self):
        clock = FakeClock(START)
        adapter, _, _ = self.adapter(
            lambda url: json_response([pair_payload()]), clock=clock
        )
        clock.advance(60)
        pairs = adapter.fetch_pairs("solana", TOKEN_MINT)
        self.assertEqual(pairs[0].observed_at, START + timedelta(seconds=60))


class RugCheckTest(unittest.TestCase):
    def adapter(self, handler):
        clock = FakeClock(START)
        sleeps = []
        transport = RecordingTransport(handler)
        return (
            RugCheckAdapter(
                base_url=RC_BASE,
                transport=transport,
                caller=make_caller(clock, sleeps),
                timeout=5,
                clock=clock.now,
            ),
            transport,
        )

    def test_valid_summary_normalised(self):
        adapter, transport = self.adapter(
            lambda url: json_response(safety_payload(score=35))
        )
        assessment = adapter.fetch_safety("solana", TOKEN_MINT)
        self.assertEqual(assessment.risk_score, Decimal(35))
        self.assertFalse(assessment.rugged)
        self.assertEqual(
            transport.calls, [f"{RC_BASE}/tokens/{TOKEN_MINT}/report/summary"]
        )

    def test_missing_score_is_malformed(self):
        adapter, _ = self.adapter(lambda url: json_response({"risks": []}))
        with self.assertRaises(ExternalServiceError) as ctx:
            adapter.fetch_safety("solana", TOKEN_MINT)
        self.assertFalse(ctx.exception.retryable)

    def test_out_of_range_score_is_rejected(self):
        adapter, _ = self.adapter(lambda url: json_response(safety_payload(score=250)))
        with self.assertRaises(ExternalServiceError):
            adapter.fetch_safety("solana", TOKEN_MINT)

    def test_nan_score_is_rejected(self):
        adapter, _ = self.adapter(
            lambda url: json_response({"score_normalised": float("nan")})
        )
        with self.assertRaises(ExternalServiceError):
            adapter.fetch_safety("solana", TOKEN_MINT)

    def test_rugged_flag_true_is_honoured(self):
        adapter, _ = self.adapter(
            lambda url: json_response(safety_payload(score=90, rugged=True))
        )
        self.assertTrue(adapter.fetch_safety("solana", TOKEN_MINT).rugged)

    def test_rugged_risk_entry_marks_rugged(self):
        risks = [{"name": "Rugged", "level": "danger", "score": 20000}]
        adapter, _ = self.adapter(
            lambda url: json_response(safety_payload(score=99, risks=risks))
        )
        self.assertTrue(adapter.fetch_safety("solana", TOKEN_MINT).rugged)

    def test_non_bool_rugged_is_malformed(self):
        adapter, _ = self.adapter(
            lambda url: json_response({"score_normalised": 1, "rugged": "yes"})
        )
        with self.assertRaises(ExternalServiceError):
            adapter.fetch_safety("solana", TOKEN_MINT)

    def test_raw_score_field_is_never_used(self):
        adapter, _ = self.adapter(
            lambda url: json_response({"score": 20000, "score_normalised": 12})
        )
        self.assertEqual(
            adapter.fetch_safety("solana", TOKEN_MINT).risk_score, Decimal(12)
        )

    def test_server_error_is_retryable_and_exhausts(self):
        adapter, transport = self.adapter(lambda url: HttpResponse(503, b"", {}))
        with self.assertRaises(ExternalServiceError) as ctx:
            adapter.fetch_safety("solana", TOKEN_MINT)
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(len(transport.calls), 3)


class SolanaTrackerHolderEvidenceTest(unittest.TestCase):
    BASE = "https://data.solanatracker.io"

    def adapter(self, payload):
        clock = FakeClock(START)
        transport = RecordingTransport(lambda url: json_response(payload))
        adapter = SolanaTrackerAdapter(
            api_key="test-key",
            transport=transport,
            caller=make_caller(clock, []),
            timeout=5,
            clock=clock.now,
        )
        return adapter, transport

    def test_holder_profile_extracts_only_valid_wallet_addresses_ranked_by_amount(self):
        accounts = [
            {"owner": "Vote111111111111111111111111111111111111111", "amount": "10"},
            {"address": "11111111111111111111111111111111", "amount": "30"},
            {"wallet": "So11111111111111111111111111111111111111112", "amount": "20"},
            {"owner": "not-a-solana-address", "amount": "100"},
            {"amount": "50"},
        ]
        adapter, transport = self.adapter({"total": 500, "accounts": accounts})

        profile = adapter.holder_profile("solana", TOKEN_MINT)

        self.assertEqual(
            profile.top_holders,
            (
                "11111111111111111111111111111111",
                "So11111111111111111111111111111111111111112",
                "Vote111111111111111111111111111111111111111",
            ),
        )
        self.assertEqual(profile.holder_count, 500)
        self.assertEqual(
            transport.calls,
            [f"{self.BASE}/tokens/{TOKEN_MINT}/holders"],
        )

    def test_holder_profile_without_recognized_wallet_fields_has_no_sybil_addresses(
        self,
    ):
        adapter, _ = self.adapter(
            {
                "total": 3,
                "accounts": [
                    {"amount": "3"},
                    {"amount": "2"},
                    {"amount": "1"},
                ],
            }
        )

        profile = adapter.holder_profile("solana", TOKEN_MINT)

        self.assertEqual(profile.top_holders, ())


if __name__ == "__main__":
    unittest.main()
