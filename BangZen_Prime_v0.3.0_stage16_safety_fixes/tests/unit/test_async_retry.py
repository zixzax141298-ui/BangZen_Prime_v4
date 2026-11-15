"""Unit tests for async network retry helper."""

from __future__ import annotations

import unittest

from bangzen_prime.core.errors import CircuitOpenError, ExternalServiceError
from bangzen_prime.data.retry.async_retry import (
    async_retry,
    async_retry_result,
    is_retryable_error,
)
from bangzen_prime.data.retry.policies import RetryPolicy


class IsRetryableTests(unittest.TestCase):
    def test_external_retryable_flag(self):
        self.assertTrue(
            is_retryable_error(
                ExternalServiceError("x", service="s", retryable=True, status=503)
            )
        )
        self.assertFalse(
            is_retryable_error(
                ExternalServiceError("x", service="s", retryable=False, status=400)
            )
        )

    def test_timeout_and_connection(self):
        self.assertTrue(is_retryable_error(TimeoutError()))
        self.assertTrue(is_retryable_error(ConnectionError("reset")))
        self.assertFalse(is_retryable_error(ValueError("bad")))
        self.assertFalse(is_retryable_error(CircuitOpenError("open")))


class AsyncRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_succeeds_after_transient_failures(self):
        sleeps: list[float] = []
        calls = {"n": 0}
        outcomes = [
            ExternalServiceError("t", service="rpc", retryable=True, status=503),
            ExternalServiceError("t", service="rpc", retryable=True, status=502),
            "ok",
        ]

        async def op():
            calls["n"] += 1
            item = outcomes.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        async def sleep(d: float) -> None:
            sleeps.append(d)

        result = await async_retry(
            op,
            policy=RetryPolicy(
                max_attempts=3, base_delay_seconds=0.5, max_delay_seconds=8
            ),
            sleep=sleep,
            operation_name="test",
        )
        self.assertEqual(result, "ok")
        self.assertEqual(calls["n"], 3)
        self.assertEqual(sleeps, [0.5, 1.0])  # 0.5 * 2^0, 0.5 * 2^1

    async def test_non_retryable_not_retried(self):
        calls = {"n": 0}

        async def op():
            calls["n"] += 1
            raise ExternalServiceError(
                "nope", service="rpc", retryable=False, status=400
            )

        with self.assertRaises(ExternalServiceError):
            await async_retry(
                op,
                policy=RetryPolicy(max_attempts=5),
                sleep=lambda _d: _noop(),
            )
        self.assertEqual(calls["n"], 1)

    async def test_exhausts_and_raises(self):
        calls = {"n": 0}

        async def op():
            calls["n"] += 1
            raise ExternalServiceError(
                "down", service="rpc", retryable=True, status=503
            )

        with self.assertRaises(ExternalServiceError):
            await async_retry(
                op,
                policy=RetryPolicy(max_attempts=3, base_delay_seconds=0.1),
                sleep=lambda _d: _noop(),
            )
        self.assertEqual(calls["n"], 3)

    async def test_honors_retry_after(self):
        sleeps: list[float] = []

        async def op():
            raise ExternalServiceError(
                "rate", service="rpc", retryable=True, status=429, retry_after=2.5
            )

        async def sleep(d: float) -> None:
            sleeps.append(d)
            # stop after first sleep by switching — use max_attempts=2
            raise ExternalServiceError(
                "rate", service="rpc", retryable=True, status=429
            )

        # simpler: one failure then success with retry_after on first
        state = {"n": 0}

        async def op2():
            state["n"] += 1
            if state["n"] == 1:
                raise ExternalServiceError(
                    "rate", service="rpc", retryable=True, status=429, retry_after=2.5
                )
            return "done"

        sleeps.clear()

        async def sleep2(d: float) -> None:
            sleeps.append(d)

        result = await async_retry(
            op2,
            policy=RetryPolicy(
                max_attempts=3, base_delay_seconds=0.5, max_delay_seconds=8
            ),
            sleep=sleep2,
        )
        self.assertEqual(result, "done")
        self.assertEqual(sleeps, [2.5])

    async def test_async_retry_result_returns_outcome_on_exhaustion(self):
        async def op():
            raise ExternalServiceError("x", service="s", retryable=True, status=503)

        value, outcome = await async_retry_result(
            op,
            policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.01),
            sleep=lambda _d: _noop(),
        )
        self.assertIsNone(value)
        self.assertFalse(outcome.succeeded)
        self.assertEqual(outcome.attempts, 2)
        self.assertIsInstance(outcome.last_error, ExternalServiceError)


async def _noop() -> None:
    return None


if __name__ == "__main__":
    unittest.main()
