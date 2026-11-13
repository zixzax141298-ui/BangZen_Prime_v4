import json
import unittest
from datetime import timedelta
from decimal import Decimal

from bangzen_prime.infrastructure.adapters.market_data.lunarcrush import (
    LunarCrushSentimentAdapter,
)
from bangzen_prime.infrastructure.http import HttpResponse, TransportTimeout
from bangzen_prime.infrastructure.resilience.policies import (
    CircuitBreaker,
    FakeClock,
    HealthMonitor,
    ResilientCaller,
    RetryPolicy,
    TokenBucket,
)
from tests.support import START


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


def payload(generated, **overrides):
    data = {
        "types_sentiment": {"reddit-post": 80, "tweet": 60},
        "types_interactions": {"reddit-post": 10, "tweet": 30},
        "interactions_24h": 40,
        "num_contributors": 12,
        "num_posts": 20,
        "trend": "up",
    }
    data.update(overrides)
    return {"config": {"topic": "solana", "generated": generated}, "data": data}


def make_caller(clock):
    return ResilientCaller(
        "lunarcrush",
        retry=RetryPolicy(max_attempts=2, base_delay_seconds=0),
        limiter=TokenBucket(rate_per_minute=600, clock=clock),
        breaker=CircuitBreaker("lunarcrush", clock=clock),
        health=HealthMonitor(),
        sleep=lambda _: None,
        clock=clock,
    )


class LunarCrushSentimentTests(unittest.TestCase):
    def make_adapter(self, handler, clock=None):
        clock = clock or FakeClock(START)
        recorder = Recorder(handler)
        adapter = LunarCrushSentimentAdapter(
            api_key="SENTIMENT-SECRET",
            transport=recorder,
            caller=make_caller(clock),
            timeout=4,
            clock=clock.now,
            cache_ttl_seconds=300,
            max_age_seconds=900,
        )
        return adapter, recorder, clock

    def test_weighted_sentiment_and_auth_header(self):
        adapter, recorder, _ = self.make_adapter(
            lambda request: HttpResponse(
                200,
                json.dumps(payload(int(START.timestamp()))).encode(),
                {},
            )
        )
        result = adapter.fetch_market_sentiment()
        self.assertEqual(result.sentiment_pct, Decimal("65.00"))
        self.assertEqual(result.interactions_24h, 40)
        self.assertEqual(result.contributors_24h, 12)
        self.assertEqual(result.trend, "up")
        request = recorder.requests[0]
        self.assertEqual(request.headers["Authorization"], "Bearer SENTIMENT-SECRET")
        self.assertNotIn("SENTIMENT-SECRET", request.url)
        self.assertIn("/public/topic/solana/v1", request.url)

    def test_cache_prevents_duplicate_api_calls(self):
        adapter, recorder, clock = self.make_adapter(
            lambda request: HttpResponse(
                200,
                json.dumps(payload(int(START.timestamp()))).encode(),
                {},
            )
        )
        first = adapter.fetch_market_sentiment()
        second = adapter.fetch_market_sentiment()
        self.assertIs(first, second)
        self.assertEqual(len(recorder.requests), 1)
        clock.advance(301)
        adapter.fetch_market_sentiment()
        self.assertEqual(len(recorder.requests), 2)

    def test_stale_response_is_rejected(self):
        adapter, _, _ = self.make_adapter(
            lambda request: HttpResponse(
                200,
                json.dumps(
                    payload(int((START - timedelta(minutes=20)).timestamp()))
                ).encode(),
                {},
            )
        )
        with self.assertRaises(Exception):
            adapter.fetch_market_sentiment()

    def test_missing_weighted_sentiment_is_rejected(self):
        adapter, _, _ = self.make_adapter(
            lambda request: HttpResponse(
                200,
                json.dumps(
                    payload(int(START.timestamp()), types_interactions={})
                ).encode(),
                {},
            )
        )
        with self.assertRaises(Exception):
            adapter.fetch_market_sentiment()

    def test_timeout_is_reported_without_leaking_api_key(self):
        adapter, recorder, _ = self.make_adapter(lambda request: TransportTimeout())
        with self.assertRaises(Exception) as caught:
            adapter.fetch_market_sentiment()
        self.assertNotIn("SENTIMENT-SECRET", str(caught.exception))
        self.assertEqual(len(recorder.requests), 2)


if __name__ == "__main__":
    unittest.main()
