"""AI provider router: ordered failover, no trade authority, no key leakage."""

import unittest

from bangzen_prime.core.errors import CircuitOpenError, ConfigurationError, ExternalServiceError
from bangzen_prime.research.ai_router import AIRouter


class Fake:
    def __init__(self, name, response=None, error=None):
        self.name = name
        self.response = response
        self.error = error
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response


def http_error(status, retryable=False):
    return ExternalServiceError(f"provider status {status}", service="x", retryable=retryable, status=status)


class AIRouterTests(unittest.TestCase):
    def test_first_healthy_provider_answers_and_others_are_not_called(self):
        a, b = Fake("a", response="A"), Fake("b", response="B")
        router = AIRouter([("a", a), ("b", b)])
        self.assertEqual(router.complete("s", "u"), "A")
        self.assertEqual((a.calls, b.calls, router.last_provider), (1, 0, "a"))

    def test_quota_or_key_failure_fails_over_to_next_provider(self):
        for status in (401, 402, 403, 429):
            with self.subTest(status=status):
                a = Fake("a", error=http_error(status))
                b = Fake("b", response="B")
                router = AIRouter([("a", a), ("b", b)])
                self.assertEqual(router.complete("s", "u"), "B")
                self.assertEqual(router.last_provider, "b")

    def test_server_error_and_circuit_open_fail_over(self):
        a = Fake("a", error=http_error(503))
        b = Fake("b", error=CircuitOpenError("open"))
        c = Fake("c", response="C")
        self.assertEqual(AIRouter([("a", a), ("b", b), ("c", c)]).complete("s", "u"), "C")

    def test_retryable_network_failure_fails_over(self):
        a = Fake("a", error=ExternalServiceError("network error", service="a", retryable=True))
        b = Fake("b", response="B")
        self.assertEqual(AIRouter([("a", a), ("b", b)]).complete("s", "u"), "B")

    def test_all_providers_failing_raises_retryable_error_without_keys(self):
        a = Fake("a", error=http_error(429))
        b = Fake("b", error=http_error(401))
        with self.assertRaises(ExternalServiceError) as ctx:
            AIRouter([("a", a), ("b", b)]).complete("s", "u")
        self.assertTrue(ctx.exception.retryable)
        self.assertIn("a:429", str(ctx.exception))
        self.assertIn("b:401", str(ctx.exception))

    def test_non_failover_error_is_raised_unchanged(self):
        a = Fake("a", error=ExternalServiceError("bad", service="a", retryable=False, status=413))
        b = Fake("b", response="B")
        with self.assertRaises(ExternalServiceError):
            AIRouter([("a", a), ("b", b)]).complete("s", "u")
        self.assertEqual(b.calls, 0)

    def test_empty_or_duplicate_provider_list_is_refused(self):
        with self.assertRaises(ConfigurationError):
            AIRouter([])
        with self.assertRaises(ConfigurationError):
            AIRouter([("a", Fake("a")), ("a", Fake("a"))])

    def test_router_exposes_order_for_status_without_secrets(self):
        router = AIRouter([("anthropic", Fake("anthropic")), ("openai", Fake("openai"))])
        self.assertEqual(router.provider_order, ("anthropic", "openai"))


if __name__ == "__main__":
    unittest.main()
