import unittest

from bangzen_prime.errors import CircuitOpenError, ExternalServiceError
from bangzen_prime.infrastructure.http import HttpResponse, TransportTimeout, get_json
from bangzen_prime.infrastructure.resilience.policies import (
    CircuitBreaker,
    CircuitState,
    FakeClock,
    HealthMonitor,
    ResilientCaller,
    RetryPolicy,
    TokenBucket,
)


def caller(clock, *, attempts=3, threshold=5, rate=600, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return ResilientCaller(
        "svc", retry=RetryPolicy(max_attempts=attempts, base_delay_seconds=1.0, max_delay_seconds=8.0),
        limiter=TokenBucket(rate_per_minute=rate, clock=clock),
        breaker=CircuitBreaker("svc", failure_threshold=threshold, recovery_seconds=30, clock=clock),
        health=HealthMonitor(), sleep=sleeps.append, clock=clock), sleeps


class RetryTest(unittest.TestCase):
    def test_retryable_then_success(self):
        clock = FakeClock()
        c, sleeps = caller(clock)
        outcomes = [ExternalServiceError("x", service="svc", retryable=True, status=500), "ok"]

        def fn():
            item = outcomes.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        self.assertEqual(c.call(fn), "ok")
        self.assertEqual(sleeps, [1.0])  # exponential: base * 2**0

    def test_non_retryable_not_retried(self):
        c, sleeps = caller(FakeClock())
        calls = []

        def fn():
            calls.append(1)
            raise ExternalServiceError("bad", service="svc", retryable=False, status=404)

        with self.assertRaises(ExternalServiceError):
            c.call(fn)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])

    def test_retry_exhaustion_raises_last_error(self):
        c, sleeps = caller(FakeClock(), attempts=3)
        calls = []

        def fn():
            calls.append(1)
            raise ExternalServiceError("down", service="svc", retryable=True, status=503)

        with self.assertRaises(ExternalServiceError):
            c.call(fn)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [1.0, 2.0])

    def test_retry_after_is_honoured_and_capped(self):
        policy = RetryPolicy(max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=8.0)
        self.assertEqual(policy.delay_for(1, retry_after=3.0), 3.0)
        self.assertEqual(policy.delay_for(1, retry_after=600.0), 8.0)
        self.assertEqual(policy.delay_for(4, retry_after=None), 8.0)

    def test_invalid_policy_rejected(self):
        with self.assertRaises(ValueError):
            RetryPolicy(max_attempts=0)
        with self.assertRaises(ValueError):
            RetryPolicy(base_delay_seconds=-1)


class CircuitBreakerTest(unittest.TestCase):
    def test_opens_after_threshold_and_blocks_calls(self):
        clock = FakeClock()
        c, _ = caller(clock, attempts=1, threshold=2)

        def fail():
            raise ExternalServiceError("x", service="svc", retryable=True)

        for _ in range(2):
            with self.assertRaises(ExternalServiceError):
                c.call(fail)
        with self.assertRaises(CircuitOpenError):
            c.call(lambda: "never")

    def test_half_open_then_recovers_on_success(self):
        clock = FakeClock()
        breaker = CircuitBreaker("b", failure_threshold=1, recovery_seconds=30, clock=clock)
        breaker.record_failure()
        self.assertEqual(breaker.state, CircuitState.OPEN)
        clock.advance(29)
        self.assertEqual(breaker.state, CircuitState.OPEN)
        clock.advance(1)
        self.assertEqual(breaker.state, CircuitState.HALF_OPEN)
        breaker.record_success()
        self.assertEqual(breaker.state, CircuitState.CLOSED)

    def test_half_open_failure_reopens(self):
        clock = FakeClock()
        breaker = CircuitBreaker("b", failure_threshold=1, recovery_seconds=10, clock=clock)
        breaker.record_failure()
        clock.advance(10)
        self.assertEqual(breaker.state, CircuitState.HALF_OPEN)
        breaker.record_failure()
        self.assertEqual(breaker.state, CircuitState.OPEN)

    def test_non_retryable_errors_do_not_trip_breaker(self):
        clock = FakeClock()
        c, _ = caller(clock, attempts=1, threshold=1)
        for _ in range(3):
            with self.assertRaises(ExternalServiceError):
                c.call(lambda: (_ for _ in ()).throw(
                    ExternalServiceError("404", service="svc", retryable=False, status=404)))
        self.assertEqual(c.call(lambda: "fine"), "fine")


class LimiterAndHealthTest(unittest.TestCase):
    def test_token_bucket_exhausts_and_refills(self):
        clock = FakeClock()
        bucket = TokenBucket(rate_per_minute=60, capacity=2, clock=clock)
        self.assertTrue(bucket.acquire())
        self.assertTrue(bucket.acquire())
        self.assertFalse(bucket.acquire())
        clock.advance(1)  # 1 token per second at 60/min
        self.assertTrue(bucket.acquire())

    def test_limiter_rejects_with_retryable_429(self):
        clock = FakeClock()
        c, _ = caller(clock, rate=1)
        c.call(lambda: 1)
        with self.assertRaises(ExternalServiceError) as ctx:
            c.call(lambda: 2)
        self.assertEqual(ctx.exception.status, 429)
        self.assertTrue(ctx.exception.retryable)

    def test_invalid_rate_rejected(self):
        with self.assertRaises(ValueError):
            TokenBucket(rate_per_minute=0)

    def test_health_monitor_counts_outcomes(self):
        clock = FakeClock()
        c, _ = caller(clock, attempts=1)
        c.call(lambda: 1)
        with self.assertRaises(ExternalServiceError):
            c.call(lambda: (_ for _ in ()).throw(
                ExternalServiceError("e", service="svc", retryable=False)))
        self.assertEqual(c._health.snapshot(), {"svc": {"ok": 1, "failed": 1}})  # noqa: SLF001


class HttpMappingTest(unittest.TestCase):
    def transport(self, response):
        def t(url, timeout):
            if isinstance(response, Exception):
                raise response
            return response
        return t

    def test_success_returns_json(self):
        data = get_json(service="s", url="u", timeout=1,
                        transport=self.transport(HttpResponse(200, b'{"a": 1}', {})))
        self.assertEqual(data, {"a": 1})

    def test_429_is_retryable_and_carries_retry_after(self):
        with self.assertRaises(ExternalServiceError) as ctx:
            get_json(service="s", url="u", timeout=1,
                     transport=self.transport(HttpResponse(429, b"", {"Retry-After": "7"})))
        self.assertTrue(ctx.exception.retryable)
        self.assertEqual(ctx.exception.retry_after, 7.0)

    def test_429_with_bad_retry_after_has_none(self):
        with self.assertRaises(ExternalServiceError) as ctx:
            get_json(service="s", url="u", timeout=1,
                     transport=self.transport(HttpResponse(429, b"", {"retry-after": "soon"})))
        self.assertIsNone(ctx.exception.retry_after)

    def test_5xx_retryable_4xx_not(self):
        with self.assertRaises(ExternalServiceError) as ctx:
            get_json(service="s", url="u", timeout=1, transport=self.transport(HttpResponse(502, b"", {})))
        self.assertTrue(ctx.exception.retryable)
        with self.assertRaises(ExternalServiceError) as ctx:
            get_json(service="s", url="u", timeout=1, transport=self.transport(HttpResponse(403, b"", {})))
        self.assertFalse(ctx.exception.retryable)

    def test_timeout_is_retryable(self):
        with self.assertRaises(ExternalServiceError) as ctx:
            get_json(service="s", url="u", timeout=1, transport=self.transport(TransportTimeout()))
        self.assertTrue(ctx.exception.retryable)

    def test_malformed_json_not_retryable(self):
        with self.assertRaises(ExternalServiceError) as ctx:
            get_json(service="s", url="u", timeout=1,
                     transport=self.transport(HttpResponse(200, b"{not json", {})))
        self.assertFalse(ctx.exception.retryable)


if __name__ == "__main__":
    unittest.main()
