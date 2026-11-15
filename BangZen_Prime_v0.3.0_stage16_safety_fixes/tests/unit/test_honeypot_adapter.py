from __future__ import annotations

import asyncio
import unittest

from bangzen_prime.security.honeypot_adapter import (
    HoneypotAdapter,
)
from tests.support import START, TOKEN_MINT


class Clock:
    def __call__(self):
        return START


class FakeJupiter:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def check_dynamic_tax(self, mint):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class HoneypotAdapterFailClosedTests(unittest.TestCase):
    def run_check(self, adapter, *, force=False):
        return asyncio.run(adapter.check_honeypot(TOKEN_MINT, force=force))

    def test_explicit_false_is_the_only_safe_result(self):
        jupiter = FakeJupiter([False])
        report = self.run_check(HoneypotAdapter(jupiter, Clock()))

        self.assertTrue(report.available)
        self.assertFalse(report.is_honeypot)
        self.assertTrue(report.is_safe)
        self.assertEqual(report.reason, "safe")

    def test_explicit_true_is_available_but_not_safe(self):
        jupiter = FakeJupiter([True])
        report = self.run_check(HoneypotAdapter(jupiter, Clock()))

        self.assertTrue(report.available)
        self.assertTrue(report.is_honeypot)
        self.assertFalse(report.is_safe)
        self.assertEqual(report.reason, "tax_increase_detected")

    def test_provider_exception_is_unavailable_not_safe(self):
        jupiter = FakeJupiter([TimeoutError("provider timed out")])
        report = self.run_check(HoneypotAdapter(jupiter, Clock()))

        self.assertFalse(report.available)
        self.assertIsNone(report.is_honeypot)
        self.assertFalse(report.is_safe)
        self.assertEqual(report.reason, "provider_error_TimeoutError")

    def test_failed_check_is_not_cached_and_can_be_retried(self):
        jupiter = FakeJupiter([RuntimeError("temporary"), False])
        adapter = HoneypotAdapter(jupiter, Clock())

        first = self.run_check(adapter)
        second = self.run_check(adapter)

        self.assertFalse(first.available)
        self.assertTrue(second.is_safe)
        self.assertEqual(jupiter.calls, 2)

    def test_cache_window_is_unavailable_not_a_safe_result(self):
        jupiter = FakeJupiter([False])
        adapter = HoneypotAdapter(jupiter, Clock())

        first = self.run_check(adapter)
        second = self.run_check(adapter)

        self.assertTrue(first.is_safe)
        self.assertFalse(second.available)
        self.assertIsNone(second.is_honeypot)
        self.assertFalse(second.is_safe)
        self.assertEqual(second.reason, "check_not_repeated_cache_window")
        self.assertEqual(jupiter.calls, 1)

    def test_force_bypasses_cache_window(self):
        jupiter = FakeJupiter([False, True])
        adapter = HoneypotAdapter(jupiter, Clock())

        self.run_check(adapter)
        forced = self.run_check(adapter, force=True)

        self.assertTrue(forced.available)
        self.assertTrue(forced.is_honeypot)
        self.assertEqual(jupiter.calls, 2)

    def test_malformed_provider_value_is_unavailable(self):
        jupiter = FakeJupiter([None])
        report = self.run_check(HoneypotAdapter(jupiter, Clock()))

        self.assertFalse(report.available)
        self.assertIsNone(report.is_honeypot)
        self.assertFalse(report.is_safe)
        self.assertEqual(report.reason, "provider_response_invalid")

    def test_invalid_interval_is_rejected(self):
        for value in (0, -1, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                HoneypotAdapter(FakeJupiter([]), Clock(), check_interval_sec=value)


if __name__ == "__main__":
    unittest.main()
