"""Tests for continuous candidate discovery orchestration."""

import unittest

from bangzen_prime.application.discovery import ContinuousDiscoveryUseCase
from bangzen_prime.application.use_cases import ScanResult
from tests.support import TOKEN_MINT


class FakeFeed:
    def __init__(self, candidates):
        self.candidates = candidates
        self.calls = []

    def fetch_candidates(self, limit=30):
        self.calls.append(limit)
        return self.candidates


class FakeScanner:
    def __init__(self):
        self.calls = []

    def execute(self, chain, mints):
        self.calls.append((chain, list(mints)))
        return [ScanResult(mint, "REJECTED", ("TEST",), None, None) for mint in mints]


class FakeLifecycleRegistry:
    def __init__(self):
        self.observations = []

    def observe(self, observation):
        self.observations.append(observation)
        return True


class ContinuousDiscoveryTest(unittest.TestCase):
    def test_deduplicates_feed_and_recent_candidates(self):
        feed = FakeFeed([TOKEN_MINT, TOKEN_MINT])
        scanner = FakeScanner()
        clock = [100.0]
        use_case = ContinuousDiscoveryUseCase(
            feed=feed, scanner=scanner, clock=lambda: clock[0], dedupe_seconds=30
        )

        first = use_case.execute(limit=10)
        second = use_case.execute(limit=10)

        self.assertEqual(first.discovered, 1)
        self.assertEqual(first.scanned, 1)
        self.assertEqual(second.discovered, 1)
        self.assertEqual(second.scanned, 0)
        self.assertEqual(second.skipped_recent, 1)
        self.assertEqual(scanner.calls, [("solana", [TOKEN_MINT])])

    def test_discovery_persists_each_unique_candidate_as_discovered(self):
        from datetime import UTC, datetime

        from bangzen_prime.domain.lifecycle import LifecyclePhase

        registry = FakeLifecycleRegistry()
        feed = FakeFeed([TOKEN_MINT, TOKEN_MINT])
        scanner = FakeScanner()
        observed_at = datetime(2026, 11, 12, tzinfo=UTC)
        use_case = ContinuousDiscoveryUseCase(
            feed=feed,
            scanner=scanner,
            lifecycle_registry=registry,
            wall_clock=lambda: observed_at,
        )

        use_case.execute()

        self.assertEqual(len(registry.observations), 1)
        self.assertEqual(registry.observations[0].phase, LifecyclePhase.DISCOVERED)
        self.assertEqual(registry.observations[0].observed_at, observed_at)
        self.assertEqual(registry.observations[0].mint, TOKEN_MINT)

    def test_candidate_is_eligible_after_dedupe_window(self):
        feed = FakeFeed([TOKEN_MINT])
        scanner = FakeScanner()
        clock = [100.0]
        use_case = ContinuousDiscoveryUseCase(
            feed=feed, scanner=scanner, clock=lambda: clock[0], dedupe_seconds=10
        )

        use_case.execute()
        clock[0] = 111.0
        result = use_case.execute()

        self.assertEqual(result.scanned, 1)
        self.assertEqual(len(scanner.calls), 2)

    def test_invalid_limit_is_rejected_before_feed_call(self):
        feed = FakeFeed([TOKEN_MINT])
        scanner = FakeScanner()
        use_case = ContinuousDiscoveryUseCase(feed=feed, scanner=scanner)

        with self.assertRaises(ValueError):
            use_case.execute(limit=0)
        self.assertEqual(feed.calls, [])
        self.assertEqual(scanner.calls, [])


if __name__ == "__main__":
    unittest.main()
