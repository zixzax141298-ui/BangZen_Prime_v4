import json
import unittest
from datetime import timedelta
from decimal import Decimal

from bangzen_prime.application.ai_brain import AIBrain, TradeContext
from bangzen_prime.application.heartbeat import EmergencyLatch
from bangzen_prime.application.reconciliation import ReconciliationWorker
from bangzen_prime.errors import ConfigurationError, DomainError, ExternalServiceError
from bangzen_prime.infrastructure.adapters.chain.helius import (
    BroadcastRefused,
    HeliusRpc,
)
from bangzen_prime.infrastructure.adapters.chain.jito import JitoClient
from bangzen_prime.infrastructure.adapters.chain.jupiter import JupiterQuoteAdapter
from bangzen_prime.infrastructure.adapters.market_data.intel import (
    BirdeyeAdapter,
    SolanaTrackerAdapter,
)
from bangzen_prime.infrastructure.ai.providers import build_provider
from bangzen_prime.infrastructure.chain.grpc_stream import YellowstoneStream
from bangzen_prime.infrastructure.http import HttpResponse, TransportTimeout
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.infrastructure.resilience.policies import (
    CircuitBreaker,
    FakeClock,
    HealthMonitor,
    ResilientCaller,
    RetryPolicy,
    TokenBucket,
)
from tests.support import SOL_MINT, START, TOKEN_MINT

OWNER = "HxFLKUAmAMLz1jtT3hbvCMELwH5H9tpM2QugP8sKyfhc"
TIP_ACCOUNT = "TipAccount11111111111111111111111111111111"


class Recorder:
    def __init__(self, handler):
        self.handler = handler
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        result = self.handler(request)
        if isinstance(result, Exception):
            raise result
        return result


def ok(payload, status=200, headers=None):
    return HttpResponse(status, json.dumps(payload).encode(), headers or {})


def caller(clock, sleeps=None):
    return ResilientCaller(
        "svc",
        retry=RetryPolicy(max_attempts=2, base_delay_seconds=0),
        limiter=TokenBucket(rate_per_minute=6000, clock=clock),
        breaker=CircuitBreaker("svc", clock=clock),
        health=HealthMonitor(),
        sleep=(sleeps if sleeps is not None else []).append,
        clock=clock,
    )


class BirdeyeTest(unittest.TestCase):
    def make(self, handler):
        clock = FakeClock(START)
        rec = Recorder(handler)
        return (
            BirdeyeAdapter(
                api_key="BIRDKEY",
                transport=rec,
                caller=caller(clock),
                timeout=5,
                clock=clock.now,
            ),
            rec,
        )

    def test_overview_parsed_with_verified_headers_and_url(self):
        adapter, rec = self.make(
            lambda r: ok(
                {
                    "data": {
                        "symbol": "ABC",
                        "liquidity": 120000,
                        "v24hUSD": 300000,
                        "price": 0.0012,
                    }
                }
            )
        )
        intel = adapter.token_intel("solana", TOKEN_MINT)
        self.assertEqual(intel.liquidity_usd, Decimal(120000))
        self.assertEqual(intel.volume_24h_usd, Decimal(300000))
        req = rec.requests[0]
        self.assertEqual(req.method, "GET")
        self.assertIn("/defi/token_overview?address=" + TOKEN_MINT, req.url)
        self.assertEqual(req.headers["X-API-KEY"], "BIRDKEY")
        self.assertEqual(req.headers["x-chain"], "solana")
        self.assertNotIn("BIRDKEY", req.url)

    def test_missing_field_fails_closed(self):
        adapter, _ = self.make(lambda r: ok({"data": {"symbol": "ABC", "price": 1}}))
        with self.assertRaises(ExternalServiceError):
            adapter.token_intel("solana", TOKEN_MINT)

    def test_non_numeric_and_nan_rejected(self):
        adapter, _ = self.make(
            lambda r: ok({"data": {"liquidity": "NaN", "v24hUSD": 1, "price": 1}})
        )
        with self.assertRaises(ExternalServiceError):
            adapter.token_intel("solana", TOKEN_MINT)

    def test_rejects_bad_mint_and_chain_before_network(self):
        adapter, rec = self.make(lambda r: ok({}))
        with self.assertRaises(DomainError):
            adapter.token_intel("solana", "bad")
        with self.assertRaises(DomainError):
            adapter.token_intel("ethereum", TOKEN_MINT)
        self.assertEqual(rec.requests, [])

    def test_empty_api_key_refused_at_construction(self):
        with self.assertRaises(DomainError):
            BirdeyeAdapter(
                api_key="",
                transport=Recorder(lambda r: ok({})),
                caller=caller(FakeClock(START)),
                timeout=1,
                clock=FakeClock(START).now,
            )

    def test_timeout_retried_and_surfaces(self):
        adapter, rec = self.make(lambda r: TransportTimeout())
        with self.assertRaises(ExternalServiceError) as ctx:
            adapter.token_intel("solana", TOKEN_MINT)
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(len(rec.requests), 2)


class SolanaTrackerTest(unittest.TestCase):
    def make(self, handler):
        clock = FakeClock(START)
        self.clock = clock
        rec = Recorder(handler)
        return (
            SolanaTrackerAdapter(
                api_key="STKEY",
                transport=rec,
                caller=caller(clock),
                timeout=5,
                clock=clock.now,
            ),
            rec,
        )

    def test_holder_profile_and_top10_share(self):
        accounts = [{"wallet": f"w{i}", "amount": 10} for i in range(20)]
        adapter, rec = self.make(lambda r: ok({"total": 500, "accounts": accounts}))
        profile = adapter.holder_profile("solana", TOKEN_MINT)
        self.assertEqual(profile.holder_count, 500)
        self.assertEqual(profile.top_holder_share_pct, Decimal(50))
        self.assertEqual(rec.requests[0].headers["x-api-key"], "STKEY")
        self.assertIn(f"/tokens/{TOKEN_MINT}/holders", rec.requests[0].url)

    def test_holder_profile_cache_avoids_repeated_api_calls(self):
        accounts = [{"wallet": "w1", "amount": 10}]
        adapter, rec = self.make(lambda r: ok({"total": 1, "accounts": accounts}))
        first = adapter.holder_profile("solana", TOKEN_MINT)
        second = adapter.holder_profile("solana", TOKEN_MINT)
        self.assertIs(first, second)
        self.assertEqual(len(rec.requests), 1)
        self.clock.advance(301)
        adapter.holder_profile("solana", TOKEN_MINT)
        self.assertEqual(len(rec.requests), 2)

    def test_missing_total_rejected(self):
        adapter, _ = self.make(lambda r: ok({"accounts": []}))
        with self.assertRaises(ExternalServiceError):
            adapter.holder_profile("solana", TOKEN_MINT)

    def test_empty_accounts_gives_no_share(self):
        adapter, _ = self.make(lambda r: ok({"total": 0, "accounts": []}))
        self.assertIsNone(
            adapter.holder_profile("solana", TOKEN_MINT).top_holder_share_pct
        )

    def test_malformed_holder_account_entry_rejected(self):
        adapter, _ = self.make(
            lambda r: ok(
                {"total": 500, "accounts": [{"wallet": "w1", "amount": 10}, None]}
            )
        )
        with self.assertRaises(ExternalServiceError):
            adapter.holder_profile("solana", TOKEN_MINT)


class JupiterTest(unittest.TestCase):
    def make(self, handler, slippage=50):
        clock = FakeClock(START)
        rec = Recorder(handler)
        return (
            JupiterQuoteAdapter(
                api_key="JUPKEY",
                transport=rec,
                caller=caller(clock),
                timeout=5,
                clock=clock.now,
                slippage_bps=slippage,
            ),
            rec,
        )

    def good(self, **over):
        body = {
            "inputMint": SOL_MINT,
            "outputMint": TOKEN_MINT,
            "inAmount": "1000000",
            "outAmount": "5000000",
            "priceImpactPct": "0.12",
        }
        body.update(over)
        return body

    def test_quote_is_built_with_expiry_and_key_in_header_only(self):
        adapter, rec = self.make(lambda r: ok(self.good()))
        q = adapter.quote(SOL_MINT, TOKEN_MINT, Decimal(1000000))
        self.assertEqual(q.out_amount, Decimal(5000000))
        self.assertEqual(q.expires_at - q.quoted_at, timedelta(seconds=20))
        req = rec.requests[0]
        self.assertIn("api.jup.ag/swap/v2/quote", req.url)
        self.assertIn("slippageBps=50", req.url)
        self.assertEqual(req.headers["x-api-key"], "JUPKEY")
        self.assertNotIn("JUPKEY", req.url)

    def test_mint_mismatch_rejected(self):
        adapter, _ = self.make(lambda r: ok(self.good(outputMint=SOL_MINT)))
        with self.assertRaises(ExternalServiceError):
            adapter.quote(SOL_MINT, TOKEN_MINT, Decimal(1000000))

    def test_fractional_or_zero_amount_refused_before_network(self):
        adapter, rec = self.make(lambda r: ok(self.good()))
        for amount in (Decimal("1.5"), Decimal(0)):
            with self.subTest(amount=amount), self.assertRaises(DomainError):
                adapter.quote(SOL_MINT, TOKEN_MINT, amount)
        self.assertEqual(rec.requests, [])

    def test_zero_out_amount_rejected(self):
        adapter, _ = self.make(lambda r: ok(self.good(outAmount="0")))
        with self.assertRaises(ExternalServiceError):
            adapter.quote(SOL_MINT, TOKEN_MINT, Decimal(1000000))

    def test_slippage_bounds(self):
        with self.assertRaises(DomainError):
            self.make(lambda r: ok({}), slippage=1001)


class JitoTest(unittest.TestCase):
    def make(self, handler):
        clock = FakeClock(START)
        rec = Recorder(handler)
        return (
            JitoClient(transport=rec, caller=caller(clock), timeout=5, clock=clock.now),
            rec,
        )

    def tip_accounts_reply(self, r):
        return ok({"jsonrpc": "2.0", "id": 1, "result": [TIP_ACCOUNT] * 8})

    def test_tip_accounts_uses_verified_jsonrpc_method(self):
        client, rec = self.make(self.tip_accounts_reply)
        self.assertEqual(len(client.tip_accounts()), 8)
        body = json.loads(rec.requests[0].body)
        self.assertEqual(body["method"], "getTipAccounts")
        self.assertEqual(rec.requests[0].method, "POST")

    def test_tip_floor_converted_from_sol_to_lamports(self):
        def handler(r):
            if "tip_floor" in r.url:
                return ok([{"landed_tips_50th_percentile": 0.0001}])
            return self.tip_accounts_reply(r)

        client, _ = self.make(handler)
        self.assertEqual(client.tip_floor_lamports(), Decimal("0.0001") * 1_000_000_000)

    def test_bundle_plan_is_local_and_priced(self):
        def handler(r):
            if "tip_floor" in r.url:
                return ok([{"landed_tips_50th_percentile": 0.00001}])  # 10000 lamports
            return self.tip_accounts_reply(r)

        client, rec = self.make(handler)
        plan = client.plan_bundle(
            transaction_count=2,
            expected_gain_lamports=Decimal(60000),
            cap_lamports=50000,
            tip_account=TIP_ACCOUNT,
        )
        self.assertEqual(plan.tip_lamports, Decimal(30000))
        self.assertEqual(plan.transaction_count, 2)
        self.assertFalse(
            any(
                "sendBundle" in (r.body or b"").decode(errors="ignore")
                for r in rec.requests
            )
        )

    def test_bundle_size_and_tip_account_checked(self):
        client, _ = self.make(lambda r: ok([{"landed_tips_50th_percentile": 0}]))
        with self.assertRaises(DomainError):
            client.plan_bundle(
                transaction_count=6,
                expected_gain_lamports=Decimal(1),
                cap_lamports=10,
                tip_account=TIP_ACCOUNT,
            )
        with self.assertRaises(DomainError):
            client.plan_bundle(
                transaction_count=1,
                expected_gain_lamports=Decimal(1),
                cap_lamports=10,
                tip_account="not-base58!",
            )

    def test_malformed_tip_floor_rejected(self):
        client, _ = self.make(lambda r: ok([{"other": 1}]))
        with self.assertRaises(ExternalServiceError):
            client.tip_floor_lamports()


class HeliusTest(unittest.TestCase):
    def make(self, handler):
        clock = FakeClock(START)
        rec = Recorder(handler)
        return (
            HeliusRpc(
                api_key="HELIUSKEY",
                transport=rec,
                caller=caller(clock),
                timeout=5,
                clock=clock.now,
            ),
            rec,
        )

    def test_token_balance_sums_parsed_accounts(self):
        reply = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "value": [
                    {
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {"tokenAmount": {"uiAmountString": "1.5"}}
                                }
                            }
                        }
                    },
                    {
                        "account": {
                            "data": {
                                "parsed": {
                                    "info": {"tokenAmount": {"uiAmountString": "2"}}
                                }
                            }
                        }
                    },
                ]
            },
        }
        client, rec = self.make(lambda r: ok(reply))
        self.assertEqual(client.token_balance(OWNER, TOKEN_MINT), Decimal("3.5"))
        self.assertIn("api-key=HELIUSKEY", rec.requests[0].url)

    def test_signature_status_mapping(self):
        for level, expected in (
            ("processed", "PROCESSED"),
            ("confirmed", "CONFIRMED"),
            ("finalized", "FINALIZED"),
        ):
            client, _ = self.make(
                lambda r, level=level: ok(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "value": [{"confirmationStatus": level, "err": None}]
                        },
                    }
                )
            )
            self.assertEqual(client.signature_status("sig"), expected)
        client, _ = self.make(
            lambda r: ok({"jsonrpc": "2.0", "id": 1, "result": {"value": [None]}})
        )
        self.assertEqual(client.signature_status("sig"), "NOT_FOUND")
        client, _ = self.make(
            lambda r: ok(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "value": [{"err": {"x": 1}, "confirmationStatus": "confirmed"}]
                    },
                }
            )
        )
        self.assertEqual(client.signature_status("sig"), "FAILED")

    def test_rpc_error_object_is_not_retried(self):
        client, rec = self.make(
            lambda r: ok({"jsonrpc": "2.0", "id": 1, "error": {"code": -1}})
        )
        with self.assertRaises(ExternalServiceError):
            client.token_balance(OWNER, TOKEN_MINT)
        self.assertEqual(len(rec.requests), 1)

    def test_send_is_always_refused(self):
        client, rec = self.make(lambda r: ok({}))
        with self.assertRaises(BroadcastRefused):
            client.send(object())
        self.assertEqual(rec.requests, [])

    def test_simulate_refuses_without_signed_transaction(self):
        client, _ = self.make(lambda r: ok({}))
        result = client.simulate(object())
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "NO_SIGNED_TRANSACTION")


class ProviderTest(unittest.TestCase):
    def build(self, name, handler, model=None):
        clock = FakeClock(START)
        rec = Recorder(handler)
        provider = build_provider(
            name=name,
            api_key="PROVKEY",
            model=model,
            transport=rec,
            caller=caller(clock),
            timeout=5,
        )
        return provider, rec

    def test_each_provider_uses_its_endpoint_and_header(self):
        anthropic_reply = {
            "content": [
                {
                    "type": "text",
                    "text": '{"decision":"SKIP","confidence":0.1,"reason":"x"}',
                }
            ]
        }
        p, rec = self.build("anthropic", lambda r: ok(anthropic_reply))
        self.assertIn("SKIP", p.complete("sys", "user"))
        self.assertEqual(rec.requests[0].url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(rec.requests[0].headers["x-api-key"], "PROVKEY")
        self.assertEqual(rec.requests[0].headers["anthropic-version"], "2023-06-01")

        openai_reply = {"choices": [{"message": {"content": "{}"}}]}
        p, rec = self.build("openai", lambda r: ok(openai_reply))
        p.complete("sys", "user")
        self.assertEqual(
            rec.requests[0].url, "https://api.openai.com/v1/chat/completions"
        )
        self.assertEqual(rec.requests[0].headers["Authorization"], "Bearer PROVKEY")

        p, rec = self.build("grok", lambda r: ok(openai_reply))
        p.complete("sys", "user")
        self.assertEqual(rec.requests[0].url, "https://api.x.ai/v1/chat/completions")

    def test_model_override_from_settings(self):
        p, rec = self.build(
            "openai",
            lambda r: ok({"choices": [{"message": {"content": "{}"}}]}),
            model="gpt-x",
        )
        p.complete("s", "u")
        self.assertEqual(json.loads(rec.requests[0].body)["model"], "gpt-x")

    def test_unexpected_shape_is_error_not_crash(self):
        p, _ = self.build("anthropic", lambda r: ok({"nope": 1}))
        with self.assertRaises(ExternalServiceError):
            p.complete("s", "u")

    def test_unknown_provider_and_missing_key(self):
        with self.assertRaises(ConfigurationError):
            build_provider(
                name="bogus",
                api_key="k",
                model=None,
                transport=Recorder(lambda r: ok({})),
                caller=caller(FakeClock(START)),
                timeout=1,
            )
        with self.assertRaises(ConfigurationError):
            build_provider(
                name="grok",
                api_key="",
                model=None,
                transport=Recorder(lambda r: ok({})),
                caller=caller(FakeClock(START)),
                timeout=1,
            )

    def test_brain_with_real_provider_shape_fails_closed_on_garbage(self):
        p, _ = self.build(
            "grok", lambda r: ok({"choices": [{"message": {"content": "maybe buy?"}}]})
        )
        d = AIBrain(p, threshold=Decimal("0.6")).decide(
            TradeContext(
                mint=TOKEN_MINT,
                symbol="X",
                liquidity_usd=Decimal(1),
                volume_24h_usd=Decimal(1),
                top10_holder_share_pct=None,
                holder_count=None,
                heuristic_score=Decimal(1),
                safety_risk_score=Decimal(1),
                rugged=False,
            )
        )
        self.assertEqual(d.decision, "SKIP")


class GrpcTest(unittest.TestCase):
    def test_yellowstone_refuses_without_stubs(self):
        with self.assertRaises(ConfigurationError):
            YellowstoneStream(endpoint="https://grpc.example", token="t")

    def test_insecure_endpoint_refused(self):
        with self.assertRaises(ConfigurationError):
            YellowstoneStream(endpoint="http://grpc.example", token="t")


class ReconciliationTest(unittest.TestCase):
    class Balances:
        def __init__(self, value=None, error=False):
            self.value, self.error = value, error

        def token_balance(self, owner, mint):
            if self.error:
                raise ExternalServiceError("rpc down", service="helius", retryable=True)
            return self.value

    def setUp(self):
        self.db = Database(":memory:")
        self.db.migrate()
        self.latch = EmergencyLatch()

    def worker(self, balances):
        return ReconciliationWorker(
            db=self.db,
            balances=balances,
            owner=OWNER,
            tolerance_pct=Decimal(1),
            latch=self.latch,
        )

    def test_not_configured_does_nothing(self):
        r = self.worker(None).run_once(TOKEN_MINT, START)
        self.assertEqual(r.status, "NOT_CONFIGURED")
        self.assertFalse(self.latch.is_active)

    def test_match_within_tolerance_is_ok(self):
        r = self.worker(self.Balances(Decimal(0))).run_once(TOKEN_MINT, START)
        self.assertEqual(r.status, "OK")
        self.assertFalse(self.latch.is_active)

    def test_mismatch_triggers_emergency_stop(self):
        r = self.worker(self.Balances(Decimal(50))).run_once(TOKEN_MINT, START)
        self.assertEqual(r.status, "MISMATCH")
        self.assertTrue(self.latch.is_active)
        self.assertTrue(self.latch.reason.startswith("RECONCILIATION_MISMATCH"))

    def test_rpc_outage_is_unavailable_not_mismatch(self):
        r = self.worker(self.Balances(error=True)).run_once(TOKEN_MINT, START)
        self.assertEqual(r.status, "UNAVAILABLE")
        self.assertFalse(self.latch.is_active)

    def test_tolerance_bounds_validated(self):
        with self.assertRaises(ValueError):
            ReconciliationWorker(
                db=self.db,
                balances=None,
                owner=OWNER,
                tolerance_pct=Decimal(101),
                latch=self.latch,
            )


class OutboxSanityTest(unittest.TestCase):
    def test_no_submit_methods_exist_on_adapters(self):
        for cls in (JitoClient, JupiterQuoteAdapter, HeliusRpc):
            names = {n for n in dir(cls) if not n.startswith("_")}
            self.assertFalse(
                names
                & {"send_bundle", "sendBundle", "submit_bundle", "send_transaction"},
                cls.__name__,
            )


if __name__ == "__main__":
    unittest.main()
