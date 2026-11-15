import unittest

from bangzen_prime.core.errors import CircuitOpenError
from bangzen_prime.data.resilience import (
    CircuitBreaker,
    ResilienceConfig,
    ResiliencePolicy,
)


class ApplicationResilienceAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_config_provides_independent_default_policies(self):
        config = ResilienceConfig()
        self.assertIsNot(config.market_breaker, config.safety_breaker)

    async def test_sync_operation_returns_value(self):
        breaker = CircuitBreaker("market", ResiliencePolicy())
        self.assertEqual(await breaker.call(lambda: "ok"), "ok")

    async def test_async_operation_returns_value(self):
        breaker = CircuitBreaker("safety", ResiliencePolicy())

        async def operation():
            return "safe"

        self.assertEqual(await breaker.call(operation), "safe")

    async def test_failure_is_recorded_and_propagated(self):
        breaker = CircuitBreaker("market", ResiliencePolicy(failure_threshold=1))

        async def operation():
            raise RuntimeError("provider unavailable")

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            await breaker.call(operation)
        with self.assertRaises(CircuitOpenError):
            await breaker.call(lambda: "must not execute")

    async def test_invalid_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            ResiliencePolicy(failure_threshold=0)
        with self.assertRaises(ValueError):
            ResiliencePolicy(recovery_seconds=-1)


if __name__ == "__main__":
    unittest.main()
